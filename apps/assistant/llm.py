import logging
import os
from pathlib import Path

from django.conf import settings
from dotenv import load_dotenv
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

RETIRED_MODELS = {
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
}
DEFAULT_MODEL = "gemini-3.6-flash"


class LLMError(Exception):
    """Raised when Gemini cannot be reached or returns invalid output."""


def _load_env():
    load_dotenv(Path(settings.BASE_DIR) / ".env", override=True)


def _gemini_api_key():
    _load_env()
    return (
        os.getenv("GEMINI_API_KEY", "")
        or getattr(settings, "GEMINI_API_KEY", "")
        or ""
    ).strip()


def _gemini_model():
    _load_env()
    model = (
        os.getenv("GEMINI_MODEL", "")
        or getattr(settings, "GEMINI_MODEL", "")
        or DEFAULT_MODEL
    ).strip()
    if model in RETIRED_MODELS:
        return DEFAULT_MODEL
    return model or DEFAULT_MODEL


def _response_text(response):
    text = getattr(response, "text", None)
    if text and str(text).strip():
        return str(text).strip()
    candidates = getattr(response, "candidates", None) or []
    parts = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            value = getattr(part, "text", None)
            if value:
                parts.append(str(value))
    return "".join(parts).strip()


def call_llm(system_prompt, user_prompt):
    """Send a Gemini request. Financial numbers must never come from here."""
    api_key = _gemini_api_key()
    if not api_key:
        raise LLMError("The assistant is unavailable because Gemini is not configured.")

    model = _gemini_model()
    try:
        client = genai.Client(api_key=api_key)
        chat = client.chats.create(
            model=model,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0,
            ),
        )
        response = chat.send_message(user_prompt)
    except LLMError:
        raise
    except Exception as exc:
        logger.warning("Gemini request failed (%s): %s", type(exc).__name__, type(exc).__name__)
        raise LLMError("I could not reach the assistant right now. Please try again.") from None

    text = _response_text(response)
    if not text:
        raise LLMError("The assistant returned an unexpected answer. Please try again.")
    return text
