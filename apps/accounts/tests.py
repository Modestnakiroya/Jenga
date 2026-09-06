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

    def test_unverified_reset_cannot_change_password(self):
        self.register()
        reset = self.client.post("/api/v1/auth/reset-password/", {"phone_number": "+256700123456", "password": "NewSecurePass123!"}, format="json")
        self.assertEqual(reset.status_code, 404)
        self.authenticate()

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

class TokenLifecycleTests(APITestCase):
    def test_expired_access_token_can_be_refreshed_for_profile_access(self):
        from datetime import timedelta
        from rest_framework_simplejwt.tokens import RefreshToken

        user = User.objects.create_user(
            phone_number="+256700987654", password="LifecyclePass123!", full_name="Token Test"
        )
        BusinessProfile.objects.create(
            user=user, business_name="Test Shop", business_type="shop_owner"
        )
        refresh = RefreshToken.for_user(user)
        expired = refresh.access_token
        expired.set_exp(lifetime=timedelta(seconds=-1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired}")
        self.assertEqual(self.client.get(reverse("profile")).status_code, 401)
        self.client.credentials()
        response = self.client.post(reverse("auth-refresh"), {"refresh": str(refresh)}, format="json")
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        profile = self.client.get(reverse("profile"))
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data["id"], user.id)


class PartnerAccountTests(APITestCase):
    def setUp(self):
        from apps.accounts.models import PartnerAccount
        self.owner = User.objects.create_user("+256700111111", "PartnerTest123!", full_name="Owner")
        self.other = User.objects.create_user("+256700222222", "PartnerTest123!", full_name="Other")
        PartnerAccount.objects.create(user=self.owner, institution_name="Test SACCO", institution_type="sacco", account_name="Savings", interest_rate="4.500", minimum_deposit="10000.00")
        PartnerAccount.objects.create(user=self.other, institution_name="Other Bank", institution_type="bank", account_name="Private")

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(reverse("partner-accounts")).status_code, 401)

    def test_only_returns_current_users_accounts_and_terms(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("partner-accounts"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["institution_name"], "Test SACCO")
        self.assertEqual(response.data[0]["interest_rate"], "4.500")
        self.assertEqual(response.data[0]["minimum_deposit"], "10000.00")
        self.assertNotIn("user", response.data[0])
        self.assertEqual(self.client.post(reverse("partner-accounts"), {}, format="json").status_code, 400)

    def test_unknown_terms_are_null(self):
        self.client.force_authenticate(self.other)
        account = self.client.get(reverse("partner-accounts")).data[0]
        self.assertIsNone(account["interest_rate"])
        self.assertIsNone(account["minimum_deposit"])

    def test_invalid_terms_rejected(self):
        from apps.accounts.models import PartnerAccount
        from django.core.exceptions import ValidationError
        account = PartnerAccount(user=self.owner, institution_name="Test", institution_type="bank", account_name="Savings", interest_rate=-1, minimum_deposit=-1, account_last_four="12345")
        with self.assertRaises(ValidationError):
            account.full_clean()


    def test_create_assigns_current_user_and_validates_terms(self):
        from apps.accounts.models import PartnerAccount
        self.client.force_authenticate(self.owner)
        payload = {"institution_name": "My Bank", "institution_type": "bank", "account_name": "Savings", "user": self.other.pk, "interest_rate": "5.00", "minimum_deposit": "1000.00"}
        response = self.client.post(reverse("partner-accounts"), payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PartnerAccount.objects.get(pk=response.data["id"]).user_id, self.owner.pk)
        payload["interest_rate"] = "-1"
        self.assertEqual(self.client.post(reverse("partner-accounts"), payload, format="json").status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(reverse("partner-accounts"), payload, format="json").status_code, 401)
