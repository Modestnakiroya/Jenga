from django.urls import path
from apps.accounts.views import SaccoLoginView
from apps.accounts.views import InstitutionListView

from apps.accounts.views import PartnerAccountsView, LoginView, ProfileView, RefreshView, RegisterView

urlpatterns = [
    path("institutions/", InstitutionListView.as_view(), name="institutions"),
    path("auth/sacco/login/", SaccoLoginView.as_view(), name="auth-sacco-login"),
    path("partners/accounts/", PartnerAccountsView.as_view(), name="partner-accounts"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("profile/", ProfileView.as_view(), name="profile"),
]
