from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class CommitmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    FULFILLED = "fulfilled", "Fulfilled"
    PARTIAL = "partial", "Partial"
    MISSED = "missed", "Missed"


class Commitment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="commitments",
    )
    goal = models.ForeignKey(
        "goals.Goal",
        on_delete=models.SET_NULL,
        related_name="commitments",
        blank=True,
        null=True,
    )
    target_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    saved_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(
        max_length=16,
        choices=CommitmentStatus.choices,
        default=CommitmentStatus.PENDING,
    )
    adjustment_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["period_end", "-created_at"]

    def clean(self):
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValidationError({"period_end": "Period end must be on or after period start."})

    def __str__(self):
        return f"{self.target_amount} ({self.status})"
