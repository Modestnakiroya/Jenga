from django.contrib import admin
from django.urls import include, path

from apps.goals.views import GoalsPageView
from config.views import HomeView, ProfilePageView, PartnershipsView, AssistantPageView, PartnersView, InsightsPageView, SaccoPageView
from django.views.generic import RedirectView
from django.views.generic import TemplateView
from config.admin_workspace import workspace

urlpatterns = [
    path("admin/", workspace, name="admin-workspace"),
    path("sacco/login/", TemplateView.as_view(template_name="sacco_login.html"), name="sacco-login"),
    path("insights/", InsightsPageView.as_view(), name="insights-page"),
    path("sacco/", SaccoPageView.as_view(), name="sacco-page"),
    path("", HomeView.as_view(), name="home"),
    path("how-it-works/", RedirectView.as_view(url="/#how-it-works", permanent=False), name="how-it-works"),
    path("profile/", ProfilePageView.as_view(), name="profile-page"),
    path("goals/", GoalsPageView.as_view(), name="goals-page"),
    path("partners/", PartnersView.as_view(), name="partners"),
    path("partnerships/", PartnershipsView.as_view(), name="partnerships"),
    path("signup/", HomeView.as_view(), name="signup"),
    path("assistant/", AssistantPageView.as_view(), name="assistant-page"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.v1.urls")),
]
