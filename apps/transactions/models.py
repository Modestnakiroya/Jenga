from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class TransactionType(models.TextChoices):
    INCOME = "income", "Income"
    EXPENSE = "expense", "Expense"


class TransactionCategory(models.TextChoices):
    SALES = "sales", "Sales"
    SERVICE = "service", "Service"
    OTHER = "other", "Other"
    STOCK_INVENTORY = "stock_inventory", "Stock/Inventory"
    RENT = "rent", "Rent"
    TRANSPORT = "transport", "Transport"
    WAGES = "wages", "Wages"
    PERSONAL_WITHDRAWAL = "personal_withdrawal", "Personal Withdrawal"


INCOME_CATEGORIES = (
    TransactionCategory.SALES,
    TransactionCategory.SERVICE,
    TransactionCategory.OTHER,
)

EXPENSE_CATEGORIES = (
    TransactionCategory.STOCK_INVENTORY,
    TransactionCategory.RENT,
    TransactionCategory.TRANSPORT,
    TransactionCategory.WAGES,
    TransactionCategory.PERSONAL_WITHDRAWAL,
    TransactionCategory.OTHER,
)

CATEGORY_LABELS = dict(TransactionCategory.choices)


class Transaction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    type = models.CharField(max_length=16, choices=TransactionType.choices)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    category = models.CharField(max_length=32, choices=TransactionCategory.choices)
    description = models.TextField(blank=True)
    date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.type} {self.amount} ({self.category})"
