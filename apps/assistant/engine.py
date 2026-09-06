import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from apps.assistant.prompts import (
    HYPOTHETICAL_ALLOCATION_DISCLAIMER,
    MISSING_AMOUNT_REPLY,
    MISSING_TRANSACTION_REPLY,
    NO_GOAL_REPLY,
    NO_RETIREMENT_REPLY,
    NO_TRANSACTIONS_REPLY,
    PERSONAL_GENERAL_REPLY,
)
from apps.goals.models import Goal, GoalStatus
from apps.planning.decision_engine import assess_affordability, recommend_allocation
from apps.retirement.models import RetirementProfile
from apps.retirement.projection import PROJECTION_DISCLAIMER, calculate_retirement_projection
from apps.transactions.models import Transaction
from apps.transactions.serializers import TransactionSerializer
from apps.transactions.services import PERIOD_TYPES, calculate_financial_summary

INTENT_RECORD_TRANSACTION = "RECORD_TRANSACTION"
INTENT_CHECK_SUMMARY = "CHECK_SUMMARY"
INTENT_CAN_I_AFFORD = "CAN_I_AFFORD"
INTENT_HOW_MUCH_SAVE = "HOW_MUCH_SAVE"
INTENT_RETIREMENT_CHECK = "RETIREMENT_CHECK"
INTENT_GENERAL_QUESTION = "GENERAL_QUESTION"

VALID_INTENTS = {
    INTENT_RECORD_TRANSACTION,
    INTENT_CHECK_SUMMARY,
    INTENT_CAN_I_AFFORD,
    INTENT_HOW_MUCH_SAVE,
    INTENT_RETIREMENT_CHECK,
    INTENT_GENERAL_QUESTION,
}
CONFIDENCE_THRESHOLD = 0.7
LITERACY_QUESTION_TYPES = {"literacy", "generic", "general"}
_AMOUNT_PATTERN = re.compile(
    r"(?i)(?:ugx\s*)?(\d{1,3}(?:,\d{3})+|\d+)(\s*[km])?"
)


def money(value):
    return f"{Decimal(value):.2f}"


def json_ready(value):
    if isinstance(value, Decimal):
        return money(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def _decimal_or_none(raw):
    if raw in (None, ""):
        return None
    text = str(raw).strip().lower().replace(",", "").replace(" ", "")
    multiplier = Decimal("1")
    if text.endswith("k") and text[:-1]:
        multiplier = Decimal("1000")
        text = text[:-1]
    elif text.endswith("m") and text[:-1]:
        multiplier = Decimal("1000000")
        text = text[:-1]
    try:
        value = Decimal(text) * multiplier
    except (InvalidOperation, TypeError, ValueError):
        return None
    return value


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _parse_amount_from_text(text):
    if not text:
        return None
    best = None
    for match in _AMOUNT_PATTERN.finditer(str(text)):
        raw = match.group(1).replace(",", "")
        suffix = (match.group(2) or "").strip().lower()
        try:
            value = Decimal(raw)
        except (InvalidOperation, TypeError, ValueError):
            continue
        if suffix == "k":
            value *= Decimal("1000")
        elif suffix == "m":
            value *= Decimal("1000000")
        if value <= 0:
            continue
        if not suffix and 1900 <= value <= 2100:
            continue
        best = value
    return best


def _stated_amount(parameters, message=""):
    for key in ("amount", "stated_amount", "income_amount"):
        value = _decimal_or_none(parameters.get(key))
        if value is not None and value > 0:
            return value
    return _parse_amount_from_text(message)


def _has_transaction_history(user):
    return Transaction.objects.filter(user=user).exists()


def _hypothetical_allocation(user, amount):
    result = recommend_allocation(user, amount)
    allocation = {key: money(value) for key, value in result["allocation"].items()}
    return {
        "error": None,
        "facts": {
            "hypothetical": True,
            "disclaimer": HYPOTHETICAL_ALLOCATION_DISCLAIMER,
            "stated_amount": money(result["income_amount"]),
            "classification": result["classification"],
            "allocation": allocation,
            "explanation": result["explanation"],
        },
    }


def handle_record_transaction(user, parameters, message=""):
    payload = {
        "type": str(parameters.get("type") or "").strip().lower(),
        "amount": parameters.get("amount"),
        "category": str(parameters.get("category") or "").strip().lower().replace(" ", "_"),
        "description": parameters.get("description") or "",
    }
    parsed_date = _parse_date(parameters.get("date"))
    if parsed_date:
        payload["date"] = parsed_date.isoformat()
    serializer = TransactionSerializer(data=payload)
    if not serializer.is_valid():
        return {"error": MISSING_TRANSACTION_REPLY, "facts": {}}
    serializer.save(user=user)
    data = serializer.data
    return {
        "error": None,
        "facts": {
            "id": data["id"],
            "type": data["type"],
            "amount": data["amount"],
            "category": data["category"],
            "date": data["date"],
        },
    }


def handle_check_summary(user, parameters, message=""):
    if not _has_transaction_history(user):
        return {"error": NO_TRANSACTIONS_REPLY, "facts": {}}
    period = str(parameters.get("period") or "").strip().lower()
    if period not in PERIOD_TYPES:
        profile = getattr(user, "business_profile", None)
        period = profile.tracking_frequency if profile else "weekly"
    reference_date = _parse_date(parameters.get("date")) or timezone.localdate()
    summary = calculate_financial_summary(user, period, reference_date)
    return {
        "error": None,
        "facts": {
            "period": summary["period"],
            "period_start": summary["period_start"].isoformat(),
            "period_end": summary["period_end"].isoformat(),
            "total_income": money(summary["total_income"]),
            "total_expenses": money(summary["total_expenses"]),
            "estimated_profit": money(summary["estimated_profit"]),
            "transaction_count": summary["transaction_count"],
        },
    }


def handle_can_i_afford(user, parameters, message=""):
    amount = _stated_amount(parameters, message)
    if amount is None or amount <= 0:
        if not _has_transaction_history(user):
            return {"error": NO_TRANSACTIONS_REPLY, "facts": {}}
        return {"error": MISSING_AMOUNT_REPLY, "facts": {}}
    if not _has_transaction_history(user):
        return _hypothetical_allocation(user, amount)
    result = assess_affordability(user, amount)
    return {
        "error": None,
        "facts": {
            "requested_amount": money(result["requested_amount"]),
            "safely_available_amount": money(result["safely_available_amount"]),
            "status": result["status"],
            "cash_on_hand": money(result["cash_on_hand"]),
            "upcoming_expenses": money(result["upcoming_expenses"]),
            "emergency_reserve": money(result["emergency_reserve"]),
        },
    }


def handle_how_much_save(user, parameters, message=""):
    amount = _stated_amount(parameters, message)
    goals = Goal.objects.filter(user=user, status=GoalStatus.ACTIVE)
    name = str(parameters.get("goal_name") or "").strip()
    if name:
        goals = goals.filter(name__icontains=name)
    goal = goals.first()
    if amount is not None and (goal is None or not _has_transaction_history(user)):
        return _hypothetical_allocation(user, amount)
    if amount is None and _has_transaction_history(user):
        from apps.planning.savings_advice import savings_advice

        profile = getattr(user, "business_profile", None)
        period = profile.tracking_frequency if profile else "weekly"
        advice = savings_advice(user, period)
        if advice["status"] == "unavailable":
            return {"error": advice["explanation"], "facts": {}}
        return {"error": None, "facts": {
            "recommended_savings": advice["amount"],
            "advice_status": advice["status"],
            "explanation": advice["explanation"],
            "period": period,
        }}
    if goal is None:
        return {"error": NO_GOAL_REPLY, "facts": {}}
    remaining = goal.target_amount - goal.current_saved_amount
    if remaining < 0:
        remaining = Decimal("0.00")
    return {
        "error": None,
        "facts": {
            "name": goal.name,
            "target_amount": money(goal.target_amount),
            "current_saved_amount": money(goal.current_saved_amount),
            "remaining_amount": money(remaining),
            "progress_percentage": f"{goal.progress_percentage:.2f}",
        },
    }


def handle_retirement_check(user, parameters, message=""):
    profile = RetirementProfile.objects.filter(user=user).first()
    if profile is None:
        return {"error": NO_RETIREMENT_REPLY, "facts": {}}
    projection = calculate_retirement_projection(profile)
    return {
        "error": None,
        "facts": {
            "years_remaining": projection["years_remaining"],
            "required_monthly_contribution": money(projection["required_monthly_contribution"]),
            "current_monthly_contribution": money(profile.current_monthly_contribution),
            "on_track": projection["on_track"],
            "disclaimer": PROJECTION_DISCLAIMER,
        },
    }


def handle_general_question(user, parameters, message=""):
    question_type = str(
        parameters.get("question_type") or parameters.get("kind") or ""
    ).strip().lower()
    if question_type in LITERACY_QUESTION_TYPES:
        return {
            "error": None,
            "facts": {"question_type": "literacy"},
            "use_literacy_llm": True,
        }
    if _has_transaction_history(user):
        return handle_check_summary(user, parameters, message=message)
    return {"error": PERSONAL_GENERAL_REPLY, "facts": {"question_type": "personal"}}


HANDLERS = {
    INTENT_RECORD_TRANSACTION: handle_record_transaction,
    INTENT_CHECK_SUMMARY: handle_check_summary,
    INTENT_CAN_I_AFFORD: handle_can_i_afford,
    INTENT_HOW_MUCH_SAVE: handle_how_much_save,
    INTENT_RETIREMENT_CHECK: handle_retirement_check,
    INTENT_GENERAL_QUESTION: handle_general_question,
}


def dispatch_intent(user, intent, parameters, message=""):
    handler = HANDLERS[intent]
    return handler(user, parameters or {}, message=message)
