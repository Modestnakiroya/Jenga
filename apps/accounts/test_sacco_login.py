from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from .models import User
from apps.insights.models import Sacco, SaccoAccess


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SaccoLoginTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("+256700123456", "SecurePass123!", full_name="Representative")
        self.sacco = Sacco.objects.create(name="Member SACCO")

    def login(self, **changes):
        return self.client.post(reverse("auth-sacco-login"), {"phone_number": "0700123456", "password": "SecurePass123!", **changes}, format="json")

    def test_unapproved_user_cannot_get_sacco_tokens(self):
        response = self.login()
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)

    def test_approved_login_and_immediate_revocation(self):
        grant = SaccoAccess.objects.create(user=self.user, sacco=self.sacco)
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["access"])
        report = self.client.get(reverse("sacco-insights"))
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data["sacco"], self.sacco.name)
        grant.is_active = False
        grant.save()
        self.assertEqual(self.client.get(reverse("sacco-insights")).status_code, 403)
        self.client.credentials()
        self.assertEqual(self.login().status_code, 401)

    def test_inactive_and_wrong_password_denied(self):
        SaccoAccess.objects.create(user=self.user, sacco=self.sacco)
        self.assertEqual(self.login(password="Incorrect123!").status_code, 401)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login().status_code, 401)

    def test_sacco_is_not_an_admin(self):
        SaccoAccess.objects.create(user=self.user, sacco=self.sacco)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_public_entry_and_removed_sms_endpoints(self):
        self.assertContains(self.client.get("/sacco/login/"), 'id="sacco-login-form"')
        self.assertContains(self.client.get("/"), 'href="/sacco/login/"')
        for path in ("/api/v1/auth/request-password-otp/", "/api/v1/auth/reset-password/"):
            self.assertEqual(self.client.post(path, {}, format="json").status_code, 404)
