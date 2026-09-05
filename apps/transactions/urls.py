from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.transactions.views import FinancialSummaryView, TransactionViewSet

router = DefaultRouter()
router.register("transactions", TransactionViewSet, basename="transaction")

urlpatterns = [
    path("summary/", FinancialSummaryView.as_view(), name="financial-summary"),
] + router.urls
