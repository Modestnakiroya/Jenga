from django.urls import include, path

urlpatterns = [
    path("", include("apps.insights.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.transactions.urls")),
    path("", include("apps.goals.urls")),
    path("", include("apps.retirement.urls")),
    path("", include("apps.planning.urls")),
    path("", include("apps.commitments.urls")),
    path("", include("apps.assistant.urls")),
]
