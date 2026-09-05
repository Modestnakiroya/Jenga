import logging
import os
from pathlib import Path

import requests
from django.conf import settings
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

SUNBIRD_TRANSLATE_URL = "https://api.sunbird.ai/tasks/nllb_translate"
# Current Sunbird OpenAPI exposes POST /tasks/translate; /tasks/nllb_translate
# is still documented but currently served as a GET-only page (HTTP 405).
SUNBIRD_TRANSLATE_FALLBACK_URL = "https://api.sunbird.ai/tasks/translate"
SUNBIRD_TIMEOUT_SECONDS = 10
SOURCE_ENGLISH = "eng"

LANGUAGE_CODES = {
    "english": "eng",
    "luganda": "lug",
    "runyankole": "nyn",
    "acholi": "ach",
    "ateso": "teo",
}
_SKIP_URLS = set()


def _load_env():
    load_dotenv(Path(settings.BASE_DIR) / ".env", override=True)


def _sunbird_api_token():
    _load_env()
    return (
        os.getenv("SUNBIRD_API_TOKEN", "")
        or getattr(settings, "SUNBIRD_API_TOKEN", "")
        or ""
    ).strip()


def sunbird_language_code(preferred_language):
    return LANGUAGE_CODES.get((preferred_language or "").strip().lower(), SOURCE_ENGLISH)


def _extract_translated_text(payload):
    if not isinstance(payload, dict):
        return None
    output = payload.get("output")
    if isinstance(output, dict):
        error = output.get("Error") or output.get("error")
        if error:
            return None
        text = output.get("translated_text")
        if text and str(text).strip():
            return str(text).strip()
    text = payload.get("translated_text")
    if text and str(text).strip():
        return str(text).strip()
    return None


def translate_text(text, preferred_language, source_language=SOURCE_ENGLISH):
    """Translate finished English text via Sunbird SALT. English or errors return text as-is."""
    if not text:
        return text
    target_language = sunbird_language_code(preferred_language)
    if target_language == source_language:
        return text

    token = _sunbird_api_token()
    if not token:
        logger.warning("Sunbird translation skipped: SUNBIRD_API_TOKEN is not set.")
        return text

    configured = getattr(settings, "SUNBIRD_TRANSLATE_URL", "") or SUNBIRD_TRANSLATE_URL
    urls = []
    for url in (configured, SUNBIRD_TRANSLATE_FALLBACK_URL):
        if url and url not in urls:
            urls.append(url)

    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
    }
    payload = {
        "source_language": source_language,
        "target_language": target_language,
        "text": text,
    }

    try:
        response = None
        for index, url in enumerate(urls):
            if url in _SKIP_URLS:
                continue
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=SUNBIRD_TIMEOUT_SECONDS,
            )
            if response.status_code == 405 and index < len(urls) - 1:
                _SKIP_URLS.add(url)
                logger.warning("Sunbird %s returned 405; retrying fallback endpoint.", url)
                continue
            break
        if response is None:
            raise RuntimeError("No Sunbird translation endpoint was attempted.")
        response.raise_for_status()
        translated = _extract_translated_text(response.json())
        if not translated:
            logger.warning("Sunbird translation returned no text for target=%s.", target_language)
            return text
        return translated
    except Exception as exc:
        logger.warning(
            "Sunbird translation failed (%s); falling back to English.",
            type(exc).__name__,
        )
        return text


def localize_reply(text, preferred_language):
    return translate_text(text, preferred_language)
