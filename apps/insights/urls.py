from django.urls import path
from .views import PersonalInsightsView, SaccoInsightsView

urlpatterns = [
    path("insights/personal/", PersonalInsightsView.as_view(), name="personal-insights"),
    path("insights/sacco/", SaccoInsightsView.as_view(), name="sacco-insights"),
]
