from decimal import Decimal

from rest_framework import serializers

from apps.retirement.models import RetirementProfile
from apps.retirement.projection import PROJECTION_DISCLAIMER


class RetirementProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RetirementProfile
        fields = (
            "current_age",
            "desired_retirement_age",
            "current_savings",
            "existing_pension_balance",
            "desired_retirement_fund",
            "current_monthly_contribution",
        )

    def validate_current_savings(self, value):
        if value < 0:
            raise serializers.ValidationError("Current savings cannot be negative.")
        return value

    def validate_existing_pension_balance(self, value):
        if value < 0:
            raise serializers.ValidationError("Pension balance cannot be negative.")
        return value

    def validate_desired_retirement_fund(self, value):
        if value <= 0:
            raise serializers.ValidationError("Desired retirement fund must be greater than zero.")
        return value

    def validate_current_monthly_contribution(self, value):
        if value < 0:
            raise serializers.ValidationError("Monthly contribution cannot be negative.")
        return value

    def validate(self, attrs):
        current_age = attrs.get("current_age")
        if current_age is None and self.instance is not None:
            current_age = self.instance.current_age
        desired_age = attrs.get("desired_retirement_age")
        if desired_age is None and self.instance is not None:
            desired_age = self.instance.desired_retirement_age
        if current_age is not None and desired_age is not None and desired_age <= current_age:
            raise serializers.ValidationError(
                {
                    "desired_retirement_age": (
                        "Desired retirement age must be greater than current age."
                    )
                }
            )
        return attrs


class RetirementProjectionSerializer(serializers.Serializer):
    years_remaining = serializers.IntegerField()
    required_monthly_contribution = serializers.DecimalField(max_digits=12, decimal_places=2)
    on_track = serializers.BooleanField()
    disclaimer = serializers.CharField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["required_monthly_contribution"] = f"{Decimal(data['required_monthly_contribution']):.2f}"
        if not data.get("disclaimer"):
            data["disclaimer"] = PROJECTION_DISCLAIMER
        return data
