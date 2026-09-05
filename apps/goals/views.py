from django.views.generic import TemplateView
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

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


class GoalsPageView(TemplateView):
    template_name = "goals.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["goal_types"] = GoalType.choices
        return context
