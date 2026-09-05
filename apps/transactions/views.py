from datetime import datetime

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.transactions.models import Transaction
from apps.transactions.serializers import TransactionSerializer
from apps.transactions.services import PERIOD_TYPES, calculate_financial_summary


class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user)
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class FinancialSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = request.query_params.get("period")
        if not period:
            profile = getattr(request.user, "business_profile", None)
            period = profile.tracking_frequency if profile else "weekly"
        if period not in PERIOD_TYPES:
            return Response(
                {"period": "Period must be daily, weekly, or monthly."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_date = request.query_params.get("date")
        if raw_date:
            try:
                reference_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"date": "Date must be YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            reference_date = timezone.localdate()

        summary = calculate_financial_summary(request.user, period, reference_date)
        return Response(
            {
                "period": summary["period"],
                "period_start": summary["period_start"].isoformat(),
                "period_end": summary["period_end"].isoformat(),
                "total_income": f"{summary['total_income']:.2f}",
                "total_expenses": f"{summary['total_expenses']:.2f}",
                "estimated_profit": f"{summary['estimated_profit']:.2f}",
                "transaction_count": summary["transaction_count"],
            }
        )
