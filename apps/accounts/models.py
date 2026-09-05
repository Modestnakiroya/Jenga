from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from apps.accounts.phones import normalize_phone_number, validate_e164_phone


class Language(models.TextChoices):
    ENGLISH = "english", "English"
    LUGANDA = "luganda", "Luganda"
    RUNYANKOLE = "runyankole", "Runyankole"
    ACHOLI = "acholi", "Acholi"
    ATESO = "ateso", "Ateso"


class BusinessType(models.TextChoices):
    MARKET_VENDOR = "market_vendor", "Market vendor"
    SHOP_OWNER = "shop_owner", "Shop owner"
    FOOD_VENDOR = "food_vendor", "Food vendor"
    TAILOR = "tailor", "Tailor"
    HAIRDRESSER_BARBER = "hairdresser_barber", "Hairdresser/barber"
    MECHANIC = "mechanic", "Mechanic"
    ARTISAN = "artisan", "Artisan"
    TRADER = "trader", "Trader"
    OTHER = "other", "Other"


class TrackingFrequency(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


class UserManager(BaseUserManager):
    def _create_user(self, phone_number, password, **extra_fields):
        if not phone_number:
            raise ValueError("The phone number is required.")
        if not password:
            raise ValueError("The password is required.")

        extra_fields.setdefault("email", extra_fields.get("email") or "")
        if extra_fields["email"]:
            extra_fields["email"] = self.normalize_email(extra_fields["email"])

        user = self.model(
            phone_number=normalize_phone_number(phone_number),
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone_number, password, **extra_fields)

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(phone_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    # TODO: Add OTP/SMS phone verification before activating new accounts.
    phone_number = models.CharField(
        max_length=16,
        unique=True,
        validators=[validate_e164_phone],
    )
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    preferred_language = models.CharField(
        max_length=16,
        choices=Language.choices,
        default=Language.ENGLISH,
    )
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["full_name"]

    def __str__(self):
        return self.phone_number


class BusinessProfile(models.Model):
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="business_profile",
    )
    business_name = models.CharField(max_length=255)
    business_type = models.CharField(max_length=32, choices=BusinessType.choices)
    tracking_frequency = models.CharField(
        max_length=16,
        choices=TrackingFrequency.choices,
        default=TrackingFrequency.WEEKLY,
    )
    date_started = models.DateField(blank=True, null=True)

    def __str__(self):
        return self.business_name
