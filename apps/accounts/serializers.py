from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

from apps.accounts.models import BusinessProfile, BusinessType, Language, TrackingFrequency, User
from apps.accounts.phones import normalize_phone_number


class PhoneTokenObtainPairSerializer(TokenObtainPairSerializer):
    default_error_messages = {
        "no_active_account": "No account found for this phone number.",
        "wrong_password": "Wrong password for this phone number.",
        "inactive": "This account is inactive.",
    }

    def validate(self, attrs):
        raw_phone = attrs.get(self.username_field)
        password = attrs.get("password")
        try:
            phone = normalize_phone_number(raw_phone)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({self.username_field: exc.messages}) from exc

        try:
            user = User.objects.get(phone_number=phone)
        except User.DoesNotExist:
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )

        if not user.check_password(password):
            raise AuthenticationFailed(
                self.error_messages["wrong_password"],
                "wrong_password",
            )
        if not user.is_active:
            raise AuthenticationFailed(self.error_messages["inactive"], "inactive")

        self.user = user
        refresh = self.get_token(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class PasswordAwareRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        token = RefreshToken(attrs["refresh"])
        user = User.objects.filter(pk=token.get(api_settings.USER_ID_CLAIM)).first()
        if not user or not user.is_active or token.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password):
            raise AuthenticationFailed("Session expired. Please log in again.")
        return super().validate(attrs)


class SaccoLoginSerializer(PhoneTokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        from apps.insights.models import SaccoAccess, BankAccess
        if not (SaccoAccess.objects.filter(user=self.user, is_active=True).exists() or BankAccess.objects.filter(user=self.user, is_active=True).exists()):
            raise AuthenticationFailed("Institution access has not been approved. Contact your administrator.")
        return data


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = (
            "business_name",
            "business_type",
            "tracking_frequency",
            "date_started",
        )


class ProfileSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    def get_role(self, user):
        if user.is_superuser:
            return "admin"
        from apps.insights.models import SaccoAccess, BankAccess
        if BankAccess.objects.filter(user=user, is_active=True).exists():
            return "bank"
        return "sacco" if SaccoAccess.objects.filter(user=user, is_active=True).exists() else "user"

    business_profile = BusinessProfileSerializer()

    class Meta:
        model = User
        fields = (
            "id",
            "phone_number",
            "full_name",
            "email",
            "preferred_language",
            "share_sacco_insights",
            "role",
            "business_profile",
        )
        read_only_fields = ("id", "phone_number")

    @transaction.atomic
    def update(self, instance, validated_data):
        business_data = validated_data.pop("business_profile", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if business_data:
            profile = instance.business_profile
            for attr, value in business_data.items():
                setattr(profile, attr, value)
            profile.save()
        return instance


class RegisterSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    preferred_language = serializers.ChoiceField(
        choices=Language.choices,
        required=False,
        default=Language.ENGLISH,
    )
    business_name = serializers.CharField(max_length=255)
    business_type = serializers.ChoiceField(choices=BusinessType.choices)
    tracking_frequency = serializers.ChoiceField(
        choices=TrackingFrequency.choices,
        required=False,
        default=TrackingFrequency.WEEKLY,
    )
    date_started = serializers.DateField(required=False, allow_null=True, default=None)

    def validate_phone_number(self, value):
        try:
            normalized = normalize_phone_number(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        if User.objects.filter(phone_number=normalized).exists():
            raise serializers.ValidationError(
                "This phone number is already registered. Please log in."
            )
        return normalized

    def validate(self, attrs):
        user = User(
            phone_number=attrs["phone_number"],
            full_name=attrs["full_name"],
            email=attrs.get("email", ""),
        )
        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        business_fields = {
            "business_name": validated_data.pop("business_name"),
            "business_type": validated_data.pop("business_type"),
            "tracking_frequency": validated_data.pop("tracking_frequency"),
            "date_started": validated_data.pop("date_started", None),
        }
        user = User.objects.create_user(password=password, **validated_data)
        BusinessProfile.objects.create(user=user, **business_fields)
        return user

    def to_representation(self, instance):
        return ProfileSerializer(instance).data


class PartnerAccountSerializer(serializers.ModelSerializer):
    institution = serializers.CharField(write_only=True, required=False)

    class Meta:
        from apps.accounts.models import PartnerAccount
        model = PartnerAccount
        fields = ("id", "institution", "institution_name", "institution_type", "account_name", "account_last_four", "currency", "interest_rate", "interest_period", "minimum_deposit", "terms_updated_on", "terms_verified")
        extra_kwargs = {"institution_name": {"required": False}, "institution_type": {"required": False}}
        read_only_fields = ("id", "terms_verified")

    def validate(self, attrs):
        from apps.accounts.models import PartnerAccount
        from apps.insights.models import Bank, Sacco
        choice = attrs.pop("institution", None)
        if choice:
            try:
                kind, key = choice.split(":")
                model = {"bank": Bank, "sacco": Sacco}[kind]
                institution = model.objects.get(pk=int(key))
            except (ValueError, KeyError, Bank.DoesNotExist, Sacco.DoesNotExist):
                raise serializers.ValidationError({"institution": "Choose an institution from the list."})
            attrs["institution_name"], attrs["institution_type"] = institution.name, kind
        elif not attrs.get("institution_name") or not attrs.get("institution_type"):
            raise serializers.ValidationError({"institution": "Choose an institution."})
        account = PartnerAccount(**attrs)
        try:
            account.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs
