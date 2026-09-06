import logging
import os
import time
from pathlib import Path

from django.conf import settings
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

logger = logging.getLogger(__name__)

RETIRED_MODELS = {
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-flash-latest",
}
# gemini-2.5-flash is scheduled to shut down Oct 16, 2026 and is currently
# absorbing heavy migration traffic (common source of transient 503s).
# gemini-2.5-flash-lite / gemini-3-flash are more current options.
DEFAULT_MODEL = "gemini-2.5-flash-lite"

# Status codes worth retrying — transient/overload, not our fault
RETRYABLE_STATUS_CODES = {429, 500, 503, 504}
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.5


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
        logger.warning("Configured Gemini model '%s' is retired; using %s instead.", model, DEFAULT_MODEL)
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


def _extract_status_code(exc):
    """Pull an HTTP-ish status code out of whatever shape the SDK gives us."""
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def call_llm(system_prompt, user_prompt):
    """Send a Gemini request. Financial numbers must never come from here."""
    api_key = _gemini_api_key()
    if not api_key:
        raise LLMError("The assistant is unavailable because Gemini is not configured.")

    model = _gemini_model()
    client = genai.Client(api_key=api_key)

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            chat = client.chats.create(
                model=model,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0,
                ),
            )
            response = chat.send_message(user_prompt)
            text = _response_text(response)
            if not text:
                raise LLMError("The assistant returned an unexpected answer. Please try again.")
            return text

        except LLMError:
            raise

        except (ClientError, ServerError) as exc:
            last_exc = exc
            status = _extract_status_code(exc)
            # Log the REAL detail, not just the exception class name twice
            logger.warning(
                "Gemini request failed on attempt %d/%d — status=%s type=%s detail=%s",
                attempt, MAX_RETRIES, status, type(exc).__name__, str(exc),
            )
            if status in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                sleep_for = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                time.sleep(sleep_for)
                continue
            break

        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Gemini request failed with unexpected error: %s: %s",
                type(exc).__name__, str(exc),
            )
            break

    logger.error("Gemini request exhausted retries. Last error: %s", repr(last_exc))
    raise LLMError("I could not reach the assistant right now. Please try again.") from None