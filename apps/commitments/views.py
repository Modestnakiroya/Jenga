from django.views.generic import TemplateView
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.assistant.translations import dashboard_labels_json

from apps.commitments.models import Commitment
from apps.commitments.serializers import (
    AdjustCommitmentSerializer,
    CommitmentSerializer,
    ConfirmCommitmentSerializer,
    apply_adjustment,
    apply_confirmation,
)


class CommitmentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CommitmentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Commitment.objects.filter(user=self.request.user)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["patch"], url_path="confirm")
    def confirm(self, request, pk=None):
        commitment = self.get_object()
        serializer = ConfirmCommitmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        apply_confirmation(commitment, serializer.validated_data["saved_amount"])
        return Response(CommitmentSerializer(commitment).data)

    @action(detail=True, methods=["patch"], url_path="adjust")
    def adjust(self, request, pk=None):
        commitment = self.get_object()
        serializer = AdjustCommitmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        apply_adjustment(
            commitment,
            serializer.validated_data["reason"],
            serializer.validated_data["new_target_amount"],
        )
        return Response(CommitmentSerializer(commitment).data, status=status.HTTP_200_OK)


class CommitmentsPageView(TemplateView):
    template_name = "commitments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dashboard_labels_json"] = dashboard_labels_json()
        return context
