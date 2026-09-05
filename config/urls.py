from django.contrib import admin
from django.urls import include, path

from apps.commitments.views import CommitmentsPageView
from apps.goals.views import GoalsPageView
from config.views import HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("goals/", GoalsPageView.as_view(), name="goals-page"),
    path("commitments/", CommitmentsPageView.as_view(), name="commitments-page"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.v1.urls")),
]
