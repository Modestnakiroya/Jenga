from django.urls import path

from apps.retirement.views import RetirementProfileView, RetirementProjectionView

urlpatterns = [
    path("retirement/profile/", RetirementProfileView.as_view(), name="retirement-profile"),
    path(
        "retirement/projection/",
        RetirementProjectionView.as_view(),
        name="retirement-projection",
    ),
]
