import json
from decimal import Decimal

from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView

from apps.assistant.llm import LLMError, call_llm
from .models import SaccoAccess, BankAccess
from .services import personal_insights, sacco_report


class InsightsInput(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.ChoiceField(choices=["UGX", "USD", "KES"], default="UGX")
    months = serializers.IntegerField(min_value=1, max_value=12, default=1)
    ai_summary = serializers.BooleanField(default=False)


class PersonalInsightsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = InsightsInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        use_ai = values.pop("ai_summary")
        facts = personal_insights(request.user, **values)
        facts["ai_summary"] = None
        if use_ai:
            try:
                # Never send names, phone numbers, account identifiers or raw balances.
                facts["ai_summary"] = call_llm(
                    "Explain the supplied savings tips in two plain sentences. Do not name institutions, recommend products, supply numbers, promise returns or add facts. These are suggestions, not instructions to transact.",
                    json.dumps({"tips": facts["suggestions"]}),
                ).strip()
            except LLMError:
                facts["ai_status"] = "AI explanation unavailable; calculated insights are still available."
        return Response(facts)


class HasSaccoAccess(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_active and (SaccoAccess.objects.filter(user=request.user, is_active=True).exists() or BankAccess.objects.filter(user=request.user, is_active=True).exists()))


class SaccoInsightsView(APIView):
    permission_classes = [HasSaccoAccess]

    def get(self, request):
        grant = SaccoAccess.objects.select_related("sacco").filter(user=request.user, is_active=True).first()
        if grant is None:
            bank_grant = BankAccess.objects.select_related("bank").filter(user=request.user, is_active=True).first()
            if bank_grant:
                return Response(sacco_report(bank_grant.bank, bank=True))
            raise PermissionDenied("SACCO access is no longer active.")
        return Response(sacco_report(grant.sacco))
