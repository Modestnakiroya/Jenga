from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.transactions.models import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    Transaction,
    TransactionType,
)


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = (
            "id",
            "type",
            "amount",
            "category",
            "description",
            "date",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate_amount(self, value):
        if value is None or value <= Decimal("0"):
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_date(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError("Date cannot be in the future.")
        return value

    def validate(self, attrs):
        tx_type = attrs.get("type", getattr(self.instance, "type", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        if tx_type and category:
            allowed = INCOME_CATEGORIES if tx_type == TransactionType.INCOME else EXPENSE_CATEGORIES
            if category not in allowed:
                raise serializers.ValidationError(
                    {"category": "Category must match the selected type."}
                )
        return attrs
