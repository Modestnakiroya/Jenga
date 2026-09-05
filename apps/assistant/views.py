import json
import re

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assistant.engine import (
    CONFIDENCE_THRESHOLD,
    VALID_INTENTS,
    INTENT_GENERAL_QUESTION,
    dispatch_intent,
    json_ready,
)
from apps.assistant.llm import LLMError, call_llm
from apps.assistant.sunbird_client import localize_reply
from apps.assistant.prompts import (
    CLASSIFY_SYSTEM,
    CLASSIFY_USER,
    HYPOTHETICAL_ALLOCATION_DISCLAIMER,
    LITERACY_SYSTEM,
    LITERACY_USER,
    LOW_CONFIDENCE_REPLY,
    PHRASE_SYSTEM,
    PHRASE_USER,
)
from apps.assistant.serializers import AskSerializer


def _render(template, **values):
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def parse_classification(raw_text):
    text = (raw_text or "").strip()
    fenced = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not fenced:
        return None
    try:
        payload = json.loads(fenced.group(0))
    except json.JSONDecodeError:
        return None
    intent = str(payload.get("intent") or "").strip().upper()
    try:
        confidence = float(payload.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, dict):
        parameters = {}
    return {"intent": intent, "confidence": confidence, "parameters": parameters}


class AskView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.validated_data["message"]

        try:
            raw_classification = call_llm(
                CLASSIFY_SYSTEM,
                _render(CLASSIFY_USER, message=message),
            )
        except LLMError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        parsed = parse_classification(raw_classification)
        if (
            parsed is None
            or parsed["intent"] not in VALID_INTENTS
            or parsed["confidence"] < CONFIDENCE_THRESHOLD
        ):
            return Response(
                {
                    "intent": INTENT_GENERAL_QUESTION,
                    "reply": localize_reply(LOW_CONFIDENCE_REPLY, request.user.preferred_language),
                    "facts": {},
                }
            )

        result = dispatch_intent(
            request.user,
            parsed["intent"],
            parsed["parameters"],
            message=message,
        )
        facts = json_ready(result.get("facts") or {})
        if result.get("error"):
            return Response(
                {
                    "intent": parsed["intent"],
                    "reply": localize_reply(result["error"], request.user.preferred_language),
                    "facts": facts,
                }
            )

        try:
            if result.get("use_literacy_llm"):
                reply = call_llm(
                    LITERACY_SYSTEM,
                    _render(LITERACY_USER, message=message),
                ).strip()
            else:
                reply = call_llm(
                    PHRASE_SYSTEM,
                    _render(PHRASE_USER, message=message, facts=json.dumps(facts)),
                ).strip()
        except LLMError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if facts.get("hypothetical"):
            disclaimer = facts.get("disclaimer") or HYPOTHETICAL_ALLOCATION_DISCLAIMER
            if disclaimer.lower() not in reply.lower():
                reply = disclaimer + " " + reply

        return Response(
            {
                "intent": parsed["intent"],
                "reply": localize_reply(reply, request.user.preferred_language),
                "facts": facts,
            }
        )
