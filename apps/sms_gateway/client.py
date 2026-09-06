import logging
import os

import africastalking
from django.core.exceptions import ValidationError

from apps.accounts.phones import normalize_phone_number

logger = logging.getLogger(__name__)


def _outbound_number(phone_number):
    try:
        return normalize_phone_number(phone_number)
    except ValidationError:
        raw = str(phone_number or "").strip()
        if raw and not raw.startswith("+"):
            return f"+{raw}"
        return raw


def send_sms(phone_number, message):
    """Send an SMS via Africa's Talking. Failures are logged, never raised."""
    username = os.getenv("AT_USERNAME", "").strip()
    api_key = os.getenv("AT_API_KEY", "").strip()
    if not username or not api_key:
        logger.error("SMS send skipped: AT_USERNAME or AT_API_KEY is not set")
        print("SMS send skipped: AT_USERNAME or AT_API_KEY is not set")
        return None
    recipient = _outbound_number(phone_number)
    try:
        africastalking.initialize(username, api_key)
        response = africastalking.SMS.send(message, [recipient])
        logger.info("SMS send to %s: %s", recipient, response)
        print(f"SMS send to {recipient}: {response}")
        return response
    except Exception:
        logger.exception("Failed to send SMS to %s", recipient)
        print(f"Failed to send SMS to {recipient}")
        return None
