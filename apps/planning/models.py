from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class UpcomingExpense(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="upcoming_expenses",
    )
    description = models.TextField()
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    expected_date = models.DateField()

    class Meta:
        ordering = ["expected_date", "id"]

    def __str__(self):
        return f"{self.description} ({self.amount})"
