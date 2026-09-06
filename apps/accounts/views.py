from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import (
    PhoneTokenObtainPairSerializer,
    ProfileSerializer,
    RegisterSerializer,
    PasswordAwareRefreshSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    serializer_class = PhoneTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


class SaccoLoginView(TokenObtainPairView):
    from apps.accounts.serializers import SaccoLoginSerializer
    serializer_class = SaccoLoginSerializer
    permission_classes = [permissions.AllowAny]


class RefreshView(TokenRefreshView):
    serializer_class = PasswordAwareRefreshSerializer
    permission_classes = [permissions.AllowAny]


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class PartnerAccountsView(generics.ListCreateAPIView):
    from apps.accounts.serializers import PartnerAccountSerializer
    serializer_class = PartnerAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return self.request.user.partner_accounts.all()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class InstitutionListView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.insights.models import Bank, Sacco
        institutions = [{"id": f"{kind}:{obj.pk}", "name": obj.name, "type": kind}
                        for kind, model in [("bank", Bank), ("sacco", Sacco)]
                        for obj in model.objects.order_by("name")]
        return Response(institutions)
