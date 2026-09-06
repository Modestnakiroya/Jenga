from django.urls import path

from apps.planning.views import AllocateView, AvailableMoneyView, CanIAffordView
from apps.planning.views import SavingsAdviceView

urlpatterns = [
    path("planning/savings-advice/", SavingsAdviceView.as_view(), name="planning-savings-advice"),
    path("planning/available-money/", AvailableMoneyView.as_view(), name="planning-available-money"),
    path("planning/can-i-afford/", CanIAffordView.as_view(), name="planning-can-i-afford"),
    path("planning/allocate/", AllocateView.as_view(), name="planning-allocate"),
]
