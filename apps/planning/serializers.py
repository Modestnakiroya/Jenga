from decimal import Decimal

from rest_framework import serializers


class AffordabilityRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


def money(value):
    return f"{Decimal(value):.2f}"
