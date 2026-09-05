from django.urls import include, path

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.transactions.urls")),
    path("", include("apps.goals.urls")),
    path("", include("apps.retirement.urls")),
]
