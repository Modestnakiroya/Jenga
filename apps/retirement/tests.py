from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.retirement.models import RetirementProfile
from apps.retirement.projection import (
    ASSUMED_ANNUAL_GROWTH_RATE,
    PROJECTION_DISCLAIMER,
    calculate_retirement_projection,
)


def sample_profile(**overrides):
    values = {
        "current_age": 40,
        "desired_retirement_age": 41,
        "current_savings": Decimal("0.00"),
        "existing_pension_balance": Decimal("0.00"),
        "desired_retirement_fund": Decimal("120000.00"),
        "current_monthly_contribution": Decimal("10000.00"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class RetirementProjectionTests(TestCase):
    def test_one_year_no_existing_balances_on_track(self):
        # n = 41 - 40 = 1
        # r = 0.08
        # PV = 0 + 0 = 0
        # FV_existing = 0 * (1.08)^1 = 0
        # gap = 120000 - 0 = 120000
        # annuity_factor = ((1.08)^1 - 1) / 0.08 = 1
        # required_annual = 120000 / 1 = 120000
        # required_monthly = 120000 / 12 = 10000.00
        # on_track because 10000.00 >= 10000.00
        profile = sample_profile()
        result = calculate_retirement_projection(profile)
        self.assertEqual(ASSUMED_ANNUAL_GROWTH_RATE, Decimal("0.08"))
        self.assertEqual(result["years_remaining"], 1)
        self.assertEqual(result["required_monthly_contribution"], Decimal("10000.00"))
        self.assertTrue(result["on_track"])

    def test_two_years_with_balances_needs_attention(self):
        # n = 32 - 30 = 2
        # (1.08)^2 = 1.1664
        # PV = 10000 + 5000 = 15000
        # FV_existing = 15000 * 1.1664 = 17496.00
        # gap = 50000 - 17496 = 32504.00
        # annuity_factor = (1.1664 - 1) / 0.08 = 2.08
        # required_annual = 32504 / 2.08 = 15626.923076...
        # required_monthly = 15626.923076... / 12 = 1302.243589... → 1302.24
        # on_track is false because 1000.00 < 1302.24
        profile = sample_profile(
            current_age=30,
            desired_retirement_age=32,
            current_savings=Decimal("10000.00"),
            existing_pension_balance=Decimal("5000.00"),
            desired_retirement_fund=Decimal("50000.00"),
            current_monthly_contribution=Decimal("1000.00"),
        )
        result = calculate_retirement_projection(profile)
        self.assertEqual(result["years_remaining"], 2)
        self.assertEqual(result["required_monthly_contribution"], Decimal("1302.24"))
        self.assertFalse(result["on_track"])

    def test_five_years_already_funded(self):
        # n = 55 - 50 = 5
        # (1.08)^5 = 1.4693280768
        # PV = 200000 + 100000 = 300000
        # FV_existing = 300000 * 1.4693280768 = 440798.42304
        # gap = 200000 - 440798.42304 < 0 → required_monthly = 0.00
        # on_track is true even with a 0 contribution
        profile = sample_profile(
            current_age=50,
            desired_retirement_age=55,
            current_savings=Decimal("200000.00"),
            existing_pension_balance=Decimal("100000.00"),
            desired_retirement_fund=Decimal("200000.00"),
            current_monthly_contribution=Decimal("0.00"),
        )
        result = calculate_retirement_projection(profile)
        self.assertEqual(result["years_remaining"], 5)
        self.assertEqual(result["required_monthly_contribution"], Decimal("0.00"))
        self.assertTrue(result["on_track"])


class RetirementModelValidationTests(TestCase):
    def test_retirement_age_must_be_greater_than_current_age(self):
        user = User.objects.create_user(
            phone_number="+256700888001",
            password="SecurePass123!",
            full_name="Retiree",
        )
        profile = RetirementProfile(
            user=user,
            current_age=45,
            desired_retirement_age=45,
            desired_retirement_fund=Decimal("100000.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            profile.full_clean()
        self.assertIn("desired_retirement_age", ctx.exception.message_dict)


class RetirementAPITests(APITestCase):
    profile_url = reverse("retirement-profile")
    projection_url = reverse("retirement-projection")

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+256700888002",
            password="SecurePass123!",
            full_name="Planner",
        )

    def authenticate(self):
        response = self.client.post(
            reverse("auth-login"),
            {"phone_number": self.user.phone_number, "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def valid_payload(self, **overrides):
        payload = {
            "current_age": 40,
            "desired_retirement_age": 41,
            "current_savings": "0.00",
            "existing_pension_balance": "0.00",
            "desired_retirement_fund": "120000.00",
            "current_monthly_contribution": "10000.00",
        }
        payload.update(overrides)
        return payload

    def test_create_and_retrieve_profile(self):
        self.authenticate()
        created = self.client.post(self.profile_url, self.valid_payload(), format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["desired_retirement_age"], 41)

        retrieved = self.client.get(self.profile_url)
        self.assertEqual(retrieved.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieved.data["current_age"], 40)
        self.assertEqual(Decimal(retrieved.data["desired_retirement_fund"]), Decimal("120000.00"))

    def test_post_updates_existing_profile(self):
        self.authenticate()
        self.client.post(self.profile_url, self.valid_payload(), format="json")
        updated = self.client.post(
            self.profile_url,
            self.valid_payload(current_monthly_contribution="8000.00"),
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(updated.data["current_monthly_contribution"]), Decimal("8000.00"))
        self.assertEqual(RetirementProfile.objects.filter(user=self.user).count(), 1)

    def test_rejects_retirement_age_less_than_or_equal_to_current_age(self):
        self.authenticate()
        equal = self.client.post(
            self.profile_url,
            self.valid_payload(current_age=40, desired_retirement_age=40),
            format="json",
        )
        younger = self.client.post(
            self.profile_url,
            self.valid_payload(current_age=50, desired_retirement_age=45),
            format="json",
        )
        self.assertEqual(equal.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("desired_retirement_age", equal.data)
        self.assertEqual(younger.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("desired_retirement_age", younger.data)
        self.assertEqual(RetirementProfile.objects.count(), 0)

    def test_projection_includes_disclaimer_and_matches_hand_calculation(self):
        self.authenticate()
        self.client.post(self.profile_url, self.valid_payload(), format="json")
        response = self.client.get(self.projection_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["years_remaining"], 1)
        self.assertEqual(response.data["required_monthly_contribution"], "10000.00")
        self.assertTrue(response.data["on_track"])
        self.assertEqual(response.data["disclaimer"], PROJECTION_DISCLAIMER)
        self.assertIn("estimate", response.data["disclaimer"].lower())
        self.assertIn("not a guarantee", response.data["disclaimer"].lower())

    def test_missing_profile_returns_404(self):
        self.authenticate()
        self.assertEqual(self.client.get(self.profile_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(self.projection_url).status_code, status.HTTP_404_NOT_FOUND)
