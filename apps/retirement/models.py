from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class RetirementProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="retirement_profile",
    )
    current_age = models.PositiveIntegerField()
    desired_retirement_age = models.PositiveIntegerField()
    current_savings = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    existing_pension_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    desired_retirement_fund = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    current_monthly_contribution = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    def clean(self):
        if (
            self.current_age is not None
            and self.desired_retirement_age is not None
            and self.desired_retirement_age <= self.current_age
        ):
            raise ValidationError(
                {
                    "desired_retirement_age": (
                        "Desired retirement age must be greater than current age."
                    )
                }
            )

    def __str__(self):
        return f"Retirement profile for {self.user}"
