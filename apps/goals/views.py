from django.views.generic import TemplateView
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from decimal import Decimal

from apps.assistant.translations import dashboard_labels_json
from apps.goals.models import Goal, GoalType
from apps.goals.serializers import GoalSerializer


class GoalViewSet(viewsets.ModelViewSet):
    serializer_class = GoalSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Goal.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="add-savings")
    def add_savings(self, request, pk=None):
        class ContributionInput(serializers.Serializer):
            amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

        data = ContributionInput(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            # Lock before reading the balance so simultaneous contributions are not lost.
            from django.shortcuts import get_object_or_404
            goal = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            if goal.status == "abandoned":
                raise serializers.ValidationError({"detail": "This goal is abandoned. Choose an active goal."})
            total = goal.current_saved_amount + data.validated_data["amount"]
            if total > Decimal("9999999999.99"):
                raise serializers.ValidationError({"amount": "This contribution exceeds the supported balance."})
            goal.current_saved_amount = total
            if total >= goal.target_amount:
                goal.status = "completed"
            # save() also updates the existing consented savings snapshot.
            goal.save(update_fields=["current_saved_amount", "status"])
        return Response(self.get_serializer(goal).data)


class GoalsPageView(TemplateView):
    template_name = "goals.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["goal_types"] = GoalType.choices
        context["dashboard_labels_json"] = dashboard_labels_json()
        return context
