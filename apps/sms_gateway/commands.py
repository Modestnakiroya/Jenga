import logging
import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.phones import normalize_phone_number
from apps.assistant.translations import DASHBOARD_LABELS, ENGLISH_LABELS
from apps.sms_gateway.registration import (
    continue_registration,
    get_active_session,
    is_register_command,
    start_registration,
)
from apps.commitments.models import Commitment, CommitmentStatus
from apps.commitments.serializers import ConfirmCommitmentSerializer, apply_confirmation
from apps.goals.models import Goal, GoalStatus
from apps.planning.decision_engine import assess_affordability
from apps.retirement.models import RetirementProfile
from apps.retirement.projection import calculate_retirement_projection
from apps.transactions.models import TransactionCategory
from apps.transactions.serializers import TransactionSerializer
from apps.transactions.services import PERIOD_TYPES, calculate_financial_summary

logger = logging.getLogger(__name__)

CATEGORY_ALIASES = {
    "sales": TransactionCategory.SALES,
    "service": TransactionCategory.SERVICE,
    "other": TransactionCategory.OTHER,
    "rent": TransactionCategory.RENT,
    "transport": TransactionCategory.TRANSPORT,
    "wages": TransactionCategory.WAGES,
    "stock": TransactionCategory.STOCK_INVENTORY,
    "inventory": TransactionCategory.STOCK_INVENTORY,
    "stock_inventory": TransactionCategory.STOCK_INVENTORY,
    "personal": TransactionCategory.PERSONAL_WITHDRAWAL,
    "withdrawal": TransactionCategory.PERSONAL_WITHDRAWAL,
    "personal_withdrawal": TransactionCategory.PERSONAL_WITHDRAWAL,
}


def sms_label(language, key, **variables):
    pack = DASHBOARD_LABELS.get((language or "english").lower()) or DASHBOARD_LABELS["english"]
    text = pack.get(key) or ENGLISH_LABELS.get(key) or key
    for name, value in variables.items():
        text = str(text).replace("{" + name + "}", str(value))
    return text


def format_amount(value):
    return f"{Decimal(value):.2f}"


def format_percent(value):
    quantized = Decimal(value).quantize(Decimal("0.01"))
    if quantized == quantized.to_integral_value():
        return str(int(quantized))
    return f"{quantized:.2f}"


def parse_command(text):
    """Return (command, args) for a case-insensitive SMS body."""
    parts = (text or "").strip().split()
    if not parts:
        return "help", {}

    verb = parts[0].upper()
    if verb in {"BALANCE", "BAL"} and len(parts) == 1:
        return "balance", {}
    if verb == "GOAL" and len(parts) == 1:
        return "goal", {}
    if verb in {"RETIRE", "RETIREMENT"} and len(parts) == 1:
        return "retire", {}
    if verb == "CANIAFFORD":
        if len(parts) != 2:
            return "help", {}
        return "can_afford", {"amount": parts[1]}
    if verb == "CONFIRM":
        if len(parts) != 2:
            return "help", {}
        return "confirm", {"amount": parts[1]}
    if verb in {"INCOME", "EXPENSE"}:
        if len(parts) < 3:
            return "help", {}
        return verb.lower(), {
            "amount": parts[1],
            "category": "_".join(parts[2:]).lower(),
        }
    return "help", {}


def find_user(phone_number):
    try:
        normalized = normalize_phone_number(phone_number)
    except ValidationError:
        return None
    return User.objects.filter(phone_number=normalized).first()


def _parse_amount(raw):
    cleaned = re.sub(r"[,\s]", "", str(raw or ""))
    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, TypeError):
        return None
    if amount <= 0:
        return None
    return amount


def _resolve_category(raw):
    return CATEGORY_ALIASES.get(str(raw or "").strip().lower().replace(" ", "_"))


def _record_transaction(user, language, tx_type, amount_raw, category_raw):
    amount = _parse_amount(amount_raw)
    if amount is None:
        return sms_label(language, "sms_invalid_amount")
    category = _resolve_category(category_raw)
    if category is None:
        return sms_label(language, "sms_invalid_category")

    serializer = TransactionSerializer(
        data={
            "type": tx_type,
            "amount": str(amount),
            "category": category,
        }
    )
    if not serializer.is_valid():
        logger.info("SMS transaction rejected: %s", serializer.errors)
        if "amount" in serializer.errors:
            return sms_label(language, "sms_invalid_amount")
        if "category" in serializer.errors:
            return sms_label(language, "sms_invalid_category")
        return sms_label(language, "sms_error")

    serializer.save(user=user)
    key = "sms_income_ok" if tx_type == "income" else "sms_expense_ok"
    return sms_label(
        language,
        key,
        amount=format_amount(serializer.data["amount"]),
        category=serializer.data["category"].upper(),
    )


def _balance_reply(user, language):
    profile = getattr(user, "business_profile", None)
    period = profile.tracking_frequency if profile else "weekly"
    if period not in PERIOD_TYPES:
        period = "weekly"
    summary = calculate_financial_summary(user, period, timezone.localdate())
    return sms_label(
        language,
        "sms_balance",
        income=format_amount(summary["total_income"]),
        expenses=format_amount(summary["total_expenses"]),
        profit=format_amount(summary["estimated_profit"]),
    )


def _can_afford_reply(user, language, amount_raw):
    amount = _parse_amount(amount_raw)
    if amount is None:
        return sms_label(language, "sms_invalid_amount")
    result = assess_affordability(user, amount)
    return sms_label(
        language,
        "sms_can_afford",
        status=result["status"],
        safe=format_amount(result["safely_available_amount"]),
        amount=format_amount(result["requested_amount"]),
    )


def _goal_reply(user, language):
    goal = (
        Goal.objects.filter(user=user, status=GoalStatus.ACTIVE)
        .order_by("-created_at", "-id")
        .first()
    )
    if goal is None:
        return sms_label(language, "sms_goal_none")
    return sms_label(
        language,
        "sms_goal_ok",
        name=goal.name,
        percent=format_percent(goal.progress_percentage),
        saved=format_amount(goal.current_saved_amount),
        target=format_amount(goal.target_amount),
    )


def _retire_reply(user, language):
    profile = RetirementProfile.objects.filter(user=user).first()
    if profile is None:
        return sms_label(language, "sms_retire_none")
    try:
        projection = calculate_retirement_projection(profile)
    except ValueError:
        return sms_label(language, "sms_error")
    key = "sms_retire_on_track" if projection["on_track"] else "sms_retire_needs_attention"
    return sms_label(
        language,
        key,
        amount=format_amount(projection["required_monthly_contribution"]),
    )


def _confirm_reply(user, language, amount_raw):
    commitment = (
        Commitment.objects.filter(user=user, status=CommitmentStatus.PENDING)
        .order_by("created_at", "id")
        .first()
    )
    if commitment is None:
        return sms_label(language, "sms_confirm_none")

    cleaned = re.sub(r"[,\s]", "", str(amount_raw or ""))
    serializer = ConfirmCommitmentSerializer(data={"saved_amount": cleaned})
    if not serializer.is_valid():
        return sms_label(language, "sms_invalid_amount")

    apply_confirmation(commitment, serializer.validated_data["saved_amount"])
    result = "Fulfilled" if commitment.status == CommitmentStatus.FULFILLED else "Partial"
    return sms_label(
        language,
        "sms_confirm_ok",
        amount=format_amount(commitment.saved_amount),
        result=result,
        status=commitment.status,
    )


def handle_incoming_sms(phone_number, text):
    try:
        phone = normalize_phone_number(phone_number)
    except ValidationError:
        return sms_label("english", "sms_register_first")

    session = get_active_session(phone)
    if session is not None:
        return continue_registration(session, text)

    user = User.objects.filter(phone_number=phone).first()
    if user is None:
        if is_register_command(text):
            return start_registration(phone)
        return sms_label("english", "sms_register_first")

    if is_register_command(text):
        return sms_label((user.preferred_language or "english").lower(), "sms_already_registered")

    language = (user.preferred_language or "english").lower()
    command, args = parse_command(text)
    if command == "income":
        return _record_transaction(user, language, "income", args["amount"], args["category"])
    if command == "expense":
        return _record_transaction(user, language, "expense", args["amount"], args["category"])
    if command == "balance":
        return _balance_reply(user, language)
    if command == "can_afford":
        return _can_afford_reply(user, language, args["amount"])
    if command == "goal":
        return _goal_reply(user, language)
    if command == "retire":
        return _retire_reply(user, language)
    if command == "confirm":
        return _confirm_reply(user, language, args["amount"])
    return sms_label(language, "sms_help")
