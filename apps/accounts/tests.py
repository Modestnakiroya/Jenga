from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import BusinessProfile, TrackingFrequency, User


class AccountsAPITests(APITestCase):
    register_url = reverse("auth-register")
    login_url = reverse("auth-login")
    profile_url = reverse("profile")

    valid_payload = {
        "phone_number": "+256700123456",
        "password": "SecurePass123!",
        "full_name": "Jane Vendor",
        "business_name": "Jane's Stall",
        "business_type": "market_vendor",
        "tracking_frequency": "weekly",
    }

    def register(self, **overrides):
        payload = {**self.valid_payload, **overrides}
        return self.client.post(self.register_url, payload, format="json")

    def authenticate(self, phone_number="+256700123456", password="SecurePass123!"):
        response = self.client.post(
            self.login_url,
            {"phone_number": phone_number, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response

    def test_successful_registration_with_phone_number(self):
        response = self.register()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(BusinessProfile.objects.count(), 1)

        user = User.objects.get()
        self.assertEqual(user.phone_number, "+256700123456")
        self.assertTrue(user.check_password("SecurePass123!"))
        self.assertEqual(user.business_profile.business_name, "Jane's Stall")
        self.assertEqual(user.business_profile.tracking_frequency, TrackingFrequency.WEEKLY)
        self.assertNotIn("password", response.data)
        self.assertEqual(response.data["phone_number"], "+256700123456")

    def test_registration_with_duplicate_phone_number_fails(self):
        first = self.register()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        response = self.register(phone_number="0700123456")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone_number", response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_registration_with_invalid_phone_number_fails(self):
        response = self.register(phone_number="not-a-phone")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone_number", response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_registration_with_weak_password_fails(self):
        response = self.register(password="123")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_login_with_correct_credentials_returns_jwt(self):
        self.register()

        response = self.client.post(
            self.login_url,
            {"phone_number": "+256700123456", "password": "SecurePass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotIn("password", response.data)

    def test_login_with_local_phone_format_succeeds(self):
        self.register()
        response = self.client.post(
            self.login_url,
            {"phone_number": "0700123456", "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_reset_password_then_login(self):
        self.register()
        reset = self.client.post(
            reverse("auth-reset-password"),
            {"phone_number": "+256700123456", "password": "NewSecurePass123!"},
            format="json",
        )
        self.assertEqual(reset.status_code, status.HTTP_200_OK)

        old_password = self.client.post(
            self.login_url,
            {"phone_number": "+256700123456", "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(old_password.status_code, status.HTTP_401_UNAUTHORIZED)

        new_password = self.client.post(
            self.login_url,
            {"phone_number": "+256700123456", "password": "NewSecurePass123!"},
            format="json",
        )
        self.assertEqual(new_password.status_code, status.HTTP_200_OK)
        self.assertIn("access", new_password.data)

    def test_login_with_incorrect_password_fails(self):
        self.register()

        response = self.client.post(
            self.login_url,
            {"phone_number": "+256700123456", "password": "WrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", response.data)

    def test_login_with_unknown_phone_number_fails(self):
        response = self.client.post(
            self.login_url,
            {"phone_number": "+256700000000", "password": "SecurePass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", response.data)

    def test_profile_retrieval_requires_authentication(self):
        self.register()

        unauthenticated = self.client.get(self.profile_url)
        self.assertEqual(unauthenticated.status_code, status.HTTP_401_UNAUTHORIZED)

        self.authenticate()
        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone_number"], "+256700123456")
        self.assertEqual(response.data["full_name"], "Jane Vendor")
        self.assertEqual(response.data["business_profile"]["business_name"], "Jane's Stall")
        self.assertEqual(response.data["business_profile"]["tracking_frequency"], "weekly")
        self.assertNotIn("password", response.data)
        self.assertNotIn("password", response.data["business_profile"])

    def test_tracking_frequency_patch_persists_and_rejects_invalid_values(self):
        self.register()
        self.authenticate()

        invalid = self.client.patch(
            self.profile_url,
            {"business_profile": {"tracking_frequency": "yearly"}},
            format="json",
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            User.objects.get().business_profile.tracking_frequency,
            TrackingFrequency.WEEKLY,
        )

        response = self.client.patch(
            self.profile_url,
            {"business_profile": {"tracking_frequency": "daily"}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["business_profile"]["tracking_frequency"], "daily")
        self.assertEqual(
            User.objects.get().business_profile.tracking_frequency,
            TrackingFrequency.DAILY,
        )
        self.assertNotIn("password", response.data)
