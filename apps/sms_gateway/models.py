from django.db import models


class RegistrationStep(models.TextChoices):
    AWAITING_NAME = "awaiting_name", "Awaiting name"
    AWAITING_BUSINESS_NAME = "awaiting_business_name", "Awaiting business name"
    AWAITING_BUSINESS_TYPE = "awaiting_business_type", "Awaiting business type"
    AWAITING_TRACKING_FREQUENCY = "awaiting_tracking_frequency", "Awaiting tracking frequency"
    COMPLETE = "complete", "Complete"


class RegistrationSession(models.Model):
    phone_number = models.CharField(max_length=16, unique=True)
    current_step = models.CharField(
        max_length=32,
        choices=RegistrationStep.choices,
        default=RegistrationStep.AWAITING_NAME,
    )
    collected_full_name = models.CharField(max_length=255, blank=True)
    collected_business_name = models.CharField(max_length=255, blank=True)
    collected_business_type = models.CharField(max_length=32, blank=True)
    collected_tracking_frequency = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.phone_number} ({self.current_step})"
