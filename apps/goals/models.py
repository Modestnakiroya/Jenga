from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class GoalType(models.TextChoices):
    EMERGENCY_FUND = "emergency_fund", "Emergency Fund"
    BUSINESS_GROWTH = "business_growth", "Business Growth"
    PERSONAL = "personal", "Personal"
    OTHER = "other", "Other"


class GoalStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    ABANDONED = "abandoned", "Abandoned"


class Goal(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goals",
    )
    name = models.CharField(max_length=255)
    goal_type = models.CharField(max_length=32, choices=GoalType.choices)
    target_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    current_saved_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    target_date = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=16,
        choices=GoalStatus.choices,
        default=GoalStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def progress_percentage(self):
        if self.target_amount <= 0:
            return Decimal("0.00")
        raw = (self.current_saved_amount / self.target_amount) * Decimal("100")
        return min(Decimal("100.00"), raw.quantize(Decimal("0.01")))
