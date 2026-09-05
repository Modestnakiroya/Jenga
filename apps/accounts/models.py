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


class PartnerAccount(models.Model):
    """An account record supplied by an administrator, not a live bank connection."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="partner_accounts")
    institution_name = models.CharField(max_length=180)
    institution_type = models.CharField(max_length=8, choices=[("bank", "Bank"), ("sacco", "SACCO")])
    account_name = models.CharField(max_length=180)
    account_last_four = models.CharField(max_length=4, blank=True)
    currency = models.CharField(max_length=3, default="UGX", choices=[("UGX", "UGX"), ("USD", "USD"), ("KES", "KES")])
    interest_rate = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    interest_period = models.CharField(max_length=8, choices=[("annual", "Per year"), ("monthly", "Per month")], default="annual")
    minimum_deposit = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    terms_updated_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["institution_name", "account_name", "id"]

    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}
        if self.interest_rate is not None and not 0 <= self.interest_rate <= 100:
            errors["interest_rate"] = "Enter a percentage from 0 to 100."
        if self.minimum_deposit is not None and self.minimum_deposit < 0:
            errors["minimum_deposit"] = "Minimum deposit cannot be negative."
        if self.account_last_four and (len(self.account_last_four) != 4 or not self.account_last_four.isascii() or not self.account_last_four.isdigit()):
            errors["account_last_four"] = "Enter only the last four digits."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.institution_name} - {self.account_name}"
