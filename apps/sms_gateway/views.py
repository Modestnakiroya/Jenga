import logging

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sms_gateway.client import send_sms
from apps.sms_gateway.commands import handle_incoming_sms

logger = logging.getLogger(__name__)


class IncomingSMSView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [FormParser, MultiPartParser, JSONParser]

    def post(self, request):
        payload = request.data.dict() if hasattr(request.data, "dict") else dict(request.data)
        logger.info("Incoming SMS payload: %s", payload)

        sender = str(payload.get("from") or payload.get("sender") or "").strip()
        text = str(payload.get("text") or payload.get("message") or "").strip()
        if not sender or not text:
            return Response(
                {"detail": "from and text are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reply = handle_incoming_sms(sender, text)
        logger.info("Incoming SMS from %s: %s -> %s", sender, text, reply)
        print(f"Incoming SMS from {sender}: {text} -> {reply}")
        send_sms(sender, reply)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)
