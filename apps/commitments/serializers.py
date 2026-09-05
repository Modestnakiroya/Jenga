from decimal import Decimal

from rest_framework import serializers

from apps.commitments.models import Commitment, CommitmentStatus


class CommitmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commitment
        fields = (
            "id",
            "goal",
            "target_amount",
            "saved_amount",
            "period_start",
            "period_end",
            "status",
            "adjustment_reason",
            "created_at",
        )
        read_only_fields = ("id", "status", "adjustment_reason", "created_at")

    def validate_target_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Target amount must be greater than zero.")
        return value

    def validate_saved_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("Saved amount cannot be negative.")
        return value

    def validate_goal(self, goal):
        if goal is None:
            return goal
        user = self.context["request"].user
        if goal.user_id != user.id:
            raise serializers.ValidationError("Goal not found.")
        return goal

    def validate(self, attrs):
        start = attrs.get("period_start")
        end = attrs.get("period_end")
        if self.instance is not None:
            start = start or self.instance.period_start
            end = end or self.instance.period_end
        if start and end and end < start:
            raise serializers.ValidationError(
                {"period_end": "Period end must be on or after period start."}
            )
        return attrs


class ConfirmCommitmentSerializer(serializers.Serializer):
    saved_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )


class AdjustCommitmentSerializer(serializers.Serializer):
    reason = serializers.CharField()
    new_target_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


def apply_confirmation(commitment, saved_amount):
    commitment.saved_amount = saved_amount
    if saved_amount >= commitment.target_amount:
        commitment.status = CommitmentStatus.FULFILLED
    else:
        commitment.status = CommitmentStatus.PARTIAL
    commitment.save(update_fields=["saved_amount", "status"])
    return commitment


def apply_adjustment(commitment, reason, new_target_amount):
    commitment.target_amount = new_target_amount
    commitment.adjustment_reason = reason
    commitment.status = CommitmentStatus.PENDING
    commitment.save(update_fields=["target_amount", "adjustment_reason", "status"])
    return commitment
