from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.planning.decision_engine import (
    assess_affordability,
    calculate_safe_to_spend,
    recommend_allocation,
)
from apps.planning.serializers import AffordabilityRequestSerializer, money


def available_money_payload(breakdown):
    return {
        "safely_available_amount": money(breakdown["safely_available_amount"]),
        "cash_on_hand": money(breakdown["cash_on_hand"]),
        "total_income": money(breakdown["total_income"]),
        "total_expenses": money(breakdown["total_expenses"]),
        "upcoming_expenses": money(breakdown["upcoming_expenses"]),
        "average_monthly_income": money(breakdown["average_monthly_income"]),
        "emergency_reserve": money(breakdown["emergency_reserve"]),
    }


class AvailableMoneyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(available_money_payload(calculate_safe_to_spend(request.user)))


class CanIAffordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AffordabilityRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = assess_affordability(request.user, serializer.validated_data["amount"])
        return Response(
            {
                **available_money_payload(result),
                "requested_amount": money(result["requested_amount"]),
                "status": result["status"],
                "explanation": result["explanation"],
            }
        )


class AllocateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AffordabilityRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = recommend_allocation(request.user, serializer.validated_data["amount"])
        return Response(
            {
                "income_amount": money(result["income_amount"]),
                "classification": result["classification"],
                "trailing_average_income": money(result["trailing_average_income"]),
                "prior_periods": result["prior_periods"],
                "used_default_average": result["used_default_average"],
                "allocation": {
                    category: money(amount)
                    for category, amount in result["allocation"].items()
                },
                "explanation": result["explanation"],
            }
        )
