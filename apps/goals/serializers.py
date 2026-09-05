from decimal import Decimal

from rest_framework import serializers

from apps.goals.models import Goal


class GoalSerializer(serializers.ModelSerializer):
    progress_percentage = serializers.SerializerMethodField()
    amount_to_add = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        write_only=True,
        min_value=Decimal("0.01"),
    )

    class Meta:
        model = Goal
        fields = (
            "id",
            "name",
            "goal_type",
            "target_amount",
            "current_saved_amount",
            "amount_to_add",
            "target_date",
            "status",
            "progress_percentage",
            "created_at",
        )
        read_only_fields = ("id", "created_at", "progress_percentage")

    def get_progress_percentage(self, obj):
        return f"{obj.progress_percentage:.2f}"

    def validate_target_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Target amount must be greater than zero.")
        return value

    def validate_current_saved_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("Saved amount cannot be negative.")
        return value

    def update(self, instance, validated_data):
        amount_to_add = validated_data.pop("amount_to_add", None)
        instance = super().update(instance, validated_data)
        if amount_to_add is not None:
            instance.current_saved_amount += amount_to_add
            instance.save(update_fields=["current_saved_amount"])
        return instance
