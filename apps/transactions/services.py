from calendar import monthrange
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum

from apps.transactions.models import Transaction, TransactionType

PERIOD_DAILY = "daily"
PERIOD_WEEKLY = "weekly"
PERIOD_MONTHLY = "monthly"
PERIOD_TYPES = {PERIOD_DAILY, PERIOD_WEEKLY, PERIOD_MONTHLY}


def period_bounds(period_type, reference_date):
    """Return inclusive start and end dates for the given period."""
    if period_type == PERIOD_DAILY:
        return reference_date, reference_date
    if period_type == PERIOD_WEEKLY:
        start = reference_date - timedelta(days=reference_date.weekday())
        return start, start + timedelta(days=6)
    if period_type == PERIOD_MONTHLY:
        start = reference_date.replace(day=1)
        last_day = monthrange(reference_date.year, reference_date.month)[1]
        return start, reference_date.replace(day=last_day)
    raise ValueError(f"Unsupported period type: {period_type}")


def calculate_financial_summary(user, period_type, reference_date):
    """Aggregate income, expenses, and profit for a user in a period."""
    if period_type not in PERIOD_TYPES:
        raise ValueError(f"Unsupported period type: {period_type}")

    start, end = period_bounds(period_type, reference_date)
    queryset = Transaction.objects.filter(user=user, date__gte=start, date__lte=end)

    total_income = queryset.filter(type=TransactionType.INCOME).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")
    total_expenses = queryset.filter(type=TransactionType.EXPENSE).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    return {
        "period": period_type,
        "period_start": start,
        "period_end": end,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "estimated_profit": total_income - total_expenses,
        "transaction_count": queryset.count(),
    }
