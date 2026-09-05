from calendar import monthrange
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

from apps.planning.models import UpcomingExpense
from apps.transactions.models import Transaction, TransactionType

EMERGENCY_RESERVE_PERCENTAGE = Decimal("0.15")
YELLOW_OVERAGE_PERCENTAGE = Decimal("0.20")
LOOKBACK_MONTHS = 3
UPCOMING_EXPENSE_DAYS = 30
STATUS_GREEN = "GREEN"
STATUS_YELLOW = "YELLOW"
STATUS_RED = "RED"
MONEY = Decimal("0.01")

CLASSIFICATION_GOOD = "Good"
CLASSIFICATION_AVERAGE = "Average"
CLASSIFICATION_BAD = "Bad"
GOOD_MONTH_THRESHOLD = Decimal("1.20")
BAD_MONTH_THRESHOLD = Decimal("0.80")
MIN_PERIODS_FOR_CLASSIFICATION = 2
ALLOCATION_CATEGORIES = ("reinvestment", "personal", "emergency", "goals")
ALLOCATION_SPLITS = {
    CLASSIFICATION_GOOD: {
        "reinvestment": Decimal("0.40"),
        "personal": Decimal("0.25"),
        "emergency": Decimal("0.15"),
        "goals": Decimal("0.20"),
    },
    CLASSIFICATION_AVERAGE: {
        "reinvestment": Decimal("0.35"),
        "personal": Decimal("0.30"),
        "emergency": Decimal("0.15"),
        "goals": Decimal("0.20"),
    },
    CLASSIFICATION_BAD: {
        "reinvestment": Decimal("0.25"),
        "personal": Decimal("0.40"),
        "emergency": Decimal("0.20"),
        "goals": Decimal("0.15"),
    },
}


def _quantize(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _sum_amount(queryset):
    return queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


def calculate_safe_to_spend(user, reference_date=None):
    """Return safely available cash and the components used to compute it.

    safely_available = max(
        0,
        cash_on_hand - upcoming_expenses_next_30_days - emergency_reserve
    )

    cash_on_hand is all-time income minus all-time expenses.
    emergency_reserve is EMERGENCY_RESERVE_PERCENTAGE of average monthly
    income over the last LOOKBACK_MONTHS months.
    """
    today = reference_date or timezone.localdate()
    transactions = Transaction.objects.filter(user=user, date__lte=today)
    total_income = _sum_amount(transactions.filter(type=TransactionType.INCOME))
    total_expenses = _sum_amount(transactions.filter(type=TransactionType.EXPENSE))
    cash_on_hand = _quantize(total_income - total_expenses)

    horizon = today + timedelta(days=UPCOMING_EXPENSE_DAYS)
    upcoming_expenses = _quantize(
        _sum_amount(
            UpcomingExpense.objects.filter(
                user=user,
                expected_date__gte=today,
                expected_date__lte=horizon,
            )
        )
    )

    window_start = _add_months(today, -LOOKBACK_MONTHS)
    recent_income = _sum_amount(
        transactions.filter(
            type=TransactionType.INCOME,
            date__gte=window_start,
        )
    )
    average_monthly_income = _quantize(recent_income / Decimal(LOOKBACK_MONTHS))
    emergency_reserve = _quantize(average_monthly_income * EMERGENCY_RESERVE_PERCENTAGE)

    raw_available = cash_on_hand - upcoming_expenses - emergency_reserve
    safely_available_amount = max(Decimal("0.00"), _quantize(raw_available))

    return {
        "safely_available_amount": safely_available_amount,
        "cash_on_hand": cash_on_hand,
        "total_income": _quantize(total_income),
        "total_expenses": _quantize(total_expenses),
        "upcoming_expenses": upcoming_expenses,
        "average_monthly_income": average_monthly_income,
        "emergency_reserve": emergency_reserve,
    }


def assess_affordability(user, requested_amount, reference_date=None):
    """Classify a purchase as GREEN, YELLOW, or RED against safe-to-spend."""
    breakdown = calculate_safe_to_spend(user, reference_date=reference_date)
    safe = breakdown["safely_available_amount"]
    requested = _quantize(requested_amount)
    yellow_limit = _quantize(safe * (Decimal("1") + YELLOW_OVERAGE_PERCENTAGE))

    if requested <= safe:
        status = STATUS_GREEN
        explanation = (
            f"This amount is within your safely available amount of {safe}."
        )
    elif requested <= yellow_limit:
        status = STATUS_YELLOW
        explanation = (
            f"This amount is up to 20 percent over your safely available amount of {safe}."
        )
    else:
        status = STATUS_RED
        explanation = (
            f"This amount is more than 20 percent over your safely available amount of {safe}."
        )

    return {
        **breakdown,
        "requested_amount": requested,
        "status": status,
        "explanation": explanation,
    }


def _complete_month_window(reference_date):
    current_month_start = reference_date.replace(day=1)
    window_start = _add_months(current_month_start, -LOOKBACK_MONTHS)
    window_end = current_month_start - timedelta(days=1)
    return window_start, window_end


def _trailing_income_history(user, reference_date):
    """Income in the last 3 complete calendar months, grouped by month."""
    window_start, window_end = _complete_month_window(reference_date)
    rows = Transaction.objects.filter(
        user=user,
        type=TransactionType.INCOME,
        date__gte=window_start,
        date__lte=window_end,
    ).values_list("date", "amount")

    months = {}
    for entry_date, amount in rows:
        key = (entry_date.year, entry_date.month)
        months[key] = months.get(key, Decimal("0.00")) + amount

    total = sum(months.values(), Decimal("0.00"))
    return {
        "period_count": len(months),
        "total": total,
        "average": total / Decimal(LOOKBACK_MONTHS),
    }


def _classify_month(income_amount, history):
    if history["period_count"] < MIN_PERIODS_FOR_CLASSIFICATION:
        return CLASSIFICATION_AVERAGE, True

    average = history["average"]
    if income_amount >= average * GOOD_MONTH_THRESHOLD:
        return CLASSIFICATION_GOOD, False
    if income_amount < average * BAD_MONTH_THRESHOLD:
        return CLASSIFICATION_BAD, False
    return CLASSIFICATION_AVERAGE, False


def _split_income(income_amount, splits):
    amounts = {}
    allocated = Decimal("0.00")
    for category in ALLOCATION_CATEGORIES[:-1]:
        amounts[category] = _quantize(income_amount * splits[category])
        allocated += amounts[category]
    last_category = ALLOCATION_CATEGORIES[-1]
    amounts[last_category] = _quantize(income_amount - allocated)
    return amounts


def recommend_allocation(user, income_amount, reference_date=None):
    """Recommend a split of income_amount based on recent month quality."""
    today = reference_date or timezone.localdate()
    amount = _quantize(income_amount)
    history = _trailing_income_history(user, today)
    classification, used_default = _classify_month(amount, history)
    allocation = _split_income(amount, ALLOCATION_SPLITS[classification])

    if used_default:
        explanation = (
            "Not enough income history yet, so this uses the average-month split."
        )
    elif classification == CLASSIFICATION_GOOD:
        explanation = (
            "This is a good month compared with your recent income. "
            "Put more into the business and goals."
        )
    elif classification == CLASSIFICATION_BAD:
        explanation = (
            "This is a lean month compared with your recent income. "
            "Keep more for personal needs and emergency savings."
        )
    else:
        explanation = (
            "This is an average month compared with your recent income. "
            "Use a balanced split."
        )

    return {
        "income_amount": amount,
        "classification": classification,
        "trailing_average_income": _quantize(history["average"]),
        "prior_periods": history["period_count"],
        "used_default_average": used_default,
        "allocation": allocation,
        "explanation": explanation,
    }
