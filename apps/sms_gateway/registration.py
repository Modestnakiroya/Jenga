import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import BusinessProfile, BusinessType, Language, TrackingFrequency, User
from apps.assistant.translations import DASHBOARD_LABELS, ENGLISH_LABELS
from apps.sms_gateway.models import RegistrationSession, RegistrationStep


def _label(key, **variables):
    pack = DASHBOARD_LABELS.get("english") or ENGLISH_LABELS
    text = pack.get(key) or ENGLISH_LABELS.get(key) or key
    for name, value in variables.items():
        text = str(text).replace("{" + name + "}", str(value))
    return text


SESSION_TIMEOUT = timedelta(minutes=30)

BUSINESS_TYPE_BY_NUMBER = {
    str(index): value for index, (value, _label) in enumerate(BusinessType.choices, start=1)
}
TRACKING_FREQUENCY_BY_NUMBER = {
    str(index): value for index, (value, _label) in enumerate(TrackingFrequency.choices, start=1)
}


def is_register_command(text):
    parts = (text or "").strip().split()
    return len(parts) == 1 and parts[0].upper() == "REGISTER"


def business_type_options():
    return " ".join(
        f"{index} {label}" for index, (_value, label) in enumerate(BusinessType.choices, start=1)
    )


def _choice_number(text):
    match = re.match(r"\s*(\d+)", text or "")
    return match.group(1) if match else None


def get_active_session(phone_number):
    session = (
        RegistrationSession.objects.filter(phone_number=phone_number)
        .exclude(current_step=RegistrationStep.COMPLETE)
        .first()
    )
    if session is None:
        return None
    if timezone.now() - session.updated_at > SESSION_TIMEOUT:
        return None
    return session


def start_registration(phone_number):
    defaults = {
        "current_step": RegistrationStep.AWAITING_NAME,
        "collected_full_name": "",
        "collected_business_name": "",
        "collected_business_type": "",
        "collected_tracking_frequency": "",
    }
    session, created = RegistrationSession.objects.get_or_create(
        phone_number=phone_number,
        defaults=defaults,
    )
    if not created:
        for field, value in defaults.items():
            setattr(session, field, value)
        session.save(update_fields=[*defaults.keys(), "updated_at"])
    return _label("sms_register_welcome")


def continue_registration(session, text):
    answer = (text or "").strip()
    if session.current_step == RegistrationStep.AWAITING_NAME:
        return _collect_name(session, answer)
    if session.current_step == RegistrationStep.AWAITING_BUSINESS_NAME:
        return _collect_business_name(session, answer)
    if session.current_step == RegistrationStep.AWAITING_BUSINESS_TYPE:
        return _collect_business_type(session, answer)
    if session.current_step == RegistrationStep.AWAITING_TRACKING_FREQUENCY:
        return _collect_tracking_frequency(session, answer)
    return start_registration(session.phone_number)


def _collect_name(session, answer):
    if not answer:
        return _label("sms_register_need_name")
    session.collected_full_name = answer[:255]
    session.current_step = RegistrationStep.AWAITING_BUSINESS_NAME
    session.save(update_fields=["collected_full_name", "current_step", "updated_at"])
    return _label("sms_register_ask_business", name=session.collected_full_name)


def _collect_business_name(session, answer):
    if not answer:
        return _label("sms_register_need_business")
    session.collected_business_name = answer[:255]
    session.current_step = RegistrationStep.AWAITING_BUSINESS_TYPE
    session.save(update_fields=["collected_business_name", "current_step", "updated_at"])
    return _label("sms_register_ask_type", options=business_type_options())


def _collect_business_type(session, answer):
    choice = BUSINESS_TYPE_BY_NUMBER.get(_choice_number(answer) or "")
    if choice is None:
        return _label("sms_register_invalid_type", options=business_type_options())
    session.collected_business_type = choice
    session.current_step = RegistrationStep.AWAITING_TRACKING_FREQUENCY
    session.save(update_fields=["collected_business_type", "current_step", "updated_at"])
    return _label("sms_register_ask_frequency")


def _collect_tracking_frequency(session, answer):
    choice = TRACKING_FREQUENCY_BY_NUMBER.get(_choice_number(answer) or "")
    if choice is None:
        return _label("sms_register_invalid_frequency")
    session.collected_tracking_frequency = choice
    session.save(update_fields=["collected_tracking_frequency", "updated_at"])
    return _complete_registration(session)


def _complete_registration(session):
    with transaction.atomic():
        user = User(
            phone_number=session.phone_number,
            full_name=session.collected_full_name,
            preferred_language=Language.ENGLISH,
        )
        user.set_unusable_password()
        user.save()
        BusinessProfile.objects.create(
            user=user,
            business_name=session.collected_business_name,
            business_type=session.collected_business_type,
            tracking_frequency=session.collected_tracking_frequency,
        )
        session.current_step = RegistrationStep.COMPLETE
        session.save(update_fields=["current_step", "updated_at"])
    return _label("sms_register_done", name=user.full_name)
