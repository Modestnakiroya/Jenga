from django.urls import path

from apps.accounts.views import PartnerAccountsView, LoginView, ProfileView, RefreshView, RegisterView, ResetPasswordView

urlpatterns = [
    path("partners/accounts/", PartnerAccountsView.as_view(), name="partner-accounts"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("auth/reset-password/", ResetPasswordView.as_view(), name="auth-reset-password"),
    path("profile/", ProfileView.as_view(), name="profile"),
]
