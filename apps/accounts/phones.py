import re

from django.core.exceptions import ValidationError

E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
NON_DIGITS = re.compile(r"\D")
DEFAULT_COUNTRY_CODE = "256"


def _digits(value):
    return NON_DIGITS.sub("", value)


def normalize_phone_number(value):
    """Normalize a phone number to E.164 (e.g. +2567XXXXXXXX)."""
    if value is None:
        raise ValidationError("Enter a valid phone number.", code="invalid")

    raw = str(value).strip()
    if not raw:
        raise ValidationError("Enter a valid phone number.", code="invalid")

    compact = re.sub(r"[\s\-().]", "", raw)

    if compact.startswith("00"):
        compact = f"+{_digits(compact[2:])}"
    elif compact.startswith("+"):
        compact = f"+{_digits(compact)}"
    elif compact.startswith("0"):
        compact = f"+{DEFAULT_COUNTRY_CODE}{_digits(compact[1:])}"
    elif compact.startswith(DEFAULT_COUNTRY_CODE):
        compact = f"+{_digits(compact)}"
    elif re.fullmatch(r"7\d{8}", compact):
        compact = f"+{DEFAULT_COUNTRY_CODE}{compact}"
    else:
        digits = _digits(compact)
        compact = f"+{digits}" if digits else compact

    if not E164_PATTERN.fullmatch(compact):
        raise ValidationError(
            "Enter a valid phone number in international format (e.g. +2567XXXXXXXX).",
            code="invalid",
        )
    return compact


def validate_e164_phone(value):
    normalize_phone_number(value)
