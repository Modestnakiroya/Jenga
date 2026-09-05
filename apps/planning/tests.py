from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.planning.decision_engine import (
    ALLOCATION_CATEGORIES,
    ALLOCATION_SPLITS,
    CLASSIFICATION_AVERAGE,
    CLASSIFICATION_BAD,
    CLASSIFICATION_GOOD,
    EMERGENCY_RESERVE_PERCENTAGE,
    STATUS_GREEN,
    STATUS_RED,
    STATUS_YELLOW,
    YELLOW_OVERAGE_PERCENTAGE,
    assess_affordability,
    calculate_safe_to_spend,
    recommend_allocation,
)
from apps.planning.models import UpcomingExpense
from apps.transactions.models import Transaction


class DecisionEngineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+256700777001",
            password="SecurePass123!",
            full_name="Planner",
        )
        self.today = timezone.localdate()

    def add_transaction(self, type, amount, days_ago=0, category=None):
        if category is None:
            category = "sales" if type == "income" else "rent"
        return Transaction.objects.create(
            user=self.user,
            type=type,
            amount=Decimal(amount),
            category=category,
            date=self.today - timedelta(days=days_ago),
        )

    def add_upcoming(self, amount, days_ahead, description="Rent"):
        return UpcomingExpense.objects.create(
            user=self.user,
            description=description,
            amount=Decimal(amount),
            expected_date=self.today + timedelta(days=days_ahead),
        )

    def seed_known_balances(self):
        # cash_on_hand = 100000 - 20000 = 80000
        # last-3-month income = 100000; average monthly = 100000 / 3
        # reserve = 0.15 * (100000 / 3) = 5000.00
        # upcoming in 30 days = 10000
        # safe = 80000 - 10000 - 5000 = 65000.00
        self.add_transaction("income", "100000.00", days_ago=10)
        self.add_transaction("expense", "20000.00", days_ago=5)
        self.add_upcoming("10000.00", days_ahead=7)
        return Decimal("65000.00")

    def test_constants(self):
        self.assertEqual(EMERGENCY_RESERVE_PERCENTAGE, Decimal("0.15"))
        self.assertEqual(YELLOW_OVERAGE_PERCENTAGE, Decimal("0.20"))

    def test_safe_to_spend_breakdown_and_green(self):
        safe = self.seed_known_balances()
        breakdown = calculate_safe_to_spend(self.user, reference_date=self.today)
        self.assertEqual(breakdown["cash_on_hand"], Decimal("80000.00"))
        self.assertEqual(breakdown["total_income"], Decimal("100000.00"))
        self.assertEqual(breakdown["total_expenses"], Decimal("20000.00"))
        self.assertEqual(breakdown["upcoming_expenses"], Decimal("10000.00"))
        self.assertEqual(breakdown["average_monthly_income"], Decimal("33333.33"))
        self.assertEqual(breakdown["emergency_reserve"], Decimal("5000.00"))
        self.assertEqual(breakdown["safely_available_amount"], safe)

        result = assess_affordability(self.user, safe, reference_date=self.today)
        self.assertEqual(result["status"], STATUS_GREEN)
        self.assertIn("within", result["explanation"])

    def test_yellow_when_up_to_20_percent_over(self):
        safe = self.seed_known_balances()
        just_over = safe + Decimal("0.01")
        at_limit = Decimal("78000.00")  # 65000 * 1.20

        slightly_over = assess_affordability(self.user, just_over, reference_date=self.today)
        self.assertEqual(slightly_over["status"], STATUS_YELLOW)

        at_twenty = assess_affordability(self.user, at_limit, reference_date=self.today)
        self.assertEqual(at_twenty["status"], STATUS_YELLOW)
        self.assertIn("up to 20 percent over", at_twenty["explanation"])

    def test_red_when_more_than_20_percent_over(self):
        self.seed_known_balances()
        result = assess_affordability(
            self.user,
            Decimal("78000.01"),
            reference_date=self.today,
        )
        self.assertEqual(result["status"], STATUS_RED)
        self.assertIn("more than 20 percent over", result["explanation"])

    def test_safe_to_spend_floored_at_zero(self):
        self.add_transaction("income", "1000.00", days_ago=2)
        self.add_transaction("expense", "400.00", days_ago=1)
        self.add_upcoming("500.00", days_ahead=3)
        # cash = 600; upcoming = 500; avg monthly = 1000/3 = 333.33
        # reserve = 333.33 * 0.15 = 50.00; raw = 600 - 500 - 50 = 50
        # force a negative: larger upcoming
        UpcomingExpense.objects.all().delete()
        self.add_upcoming("2000.00", days_ahead=3)
        breakdown = calculate_safe_to_spend(self.user, reference_date=self.today)
        self.assertEqual(breakdown["safely_available_amount"], Decimal("0.00"))
        self.assertLess(breakdown["cash_on_hand"] - breakdown["upcoming_expenses"], Decimal("0.00"))

        result = assess_affordability(self.user, Decimal("1.00"), reference_date=self.today)
        self.assertEqual(result["status"], STATUS_RED)

    def test_upcoming_outside_30_days_is_excluded(self):
        self.add_transaction("income", "100000.00")
        self.add_upcoming("40000.00", days_ahead=31)
        breakdown = calculate_safe_to_spend(self.user, reference_date=self.today)
        self.assertEqual(breakdown["upcoming_expenses"], Decimal("0.00"))

    def _add_income_on(self, year, month, day, amount):
        return Transaction.objects.create(
            user=self.user,
            type="income",
            amount=Decimal(amount),
            category="sales",
            date=self.today.replace(year=year, month=month, day=day),
        )

    def seed_trailing_months(self, amounts):
        """Put income on the 15th of each of the last 3 complete months."""
        current_start = self.today.replace(day=1)
        for offset, amount in zip((-3, -2, -1), amounts):
            month_index = current_start.month - 1 + offset
            year = current_start.year + month_index // 12
            month = month_index % 12 + 1
            if amount:
                self._add_income_on(year, month, 15, amount)

    def assert_allocation_sums(self, result, income_amount):
        total = sum(result["allocation"].values(), Decimal("0.00"))
        self.assertEqual(total, Decimal(income_amount))
        self.assertEqual(result["income_amount"], Decimal(income_amount))

    def test_allocation_defaults_to_average_without_enough_history(self):
        none = recommend_allocation(self.user, Decimal("10000.00"), reference_date=self.today)
        self.assertEqual(none["classification"], CLASSIFICATION_AVERAGE)
        self.assertTrue(none["used_default_average"])
        self.assert_allocation_sums(none, "10000.00")
        self.assertEqual(none["allocation"]["reinvestment"], Decimal("3500.00"))
        self.assertEqual(none["allocation"]["personal"], Decimal("3000.00"))
        self.assertEqual(none["allocation"]["emergency"], Decimal("1500.00"))
        self.assertEqual(none["allocation"]["goals"], Decimal("2000.00"))

        self.seed_trailing_months((None, "9000.00", None))
        one = recommend_allocation(self.user, Decimal("20000.00"), reference_date=self.today)
        self.assertEqual(one["classification"], CLASSIFICATION_AVERAGE)
        self.assertTrue(one["used_default_average"])
        self.assertEqual(one["prior_periods"], 1)
        self.assert_allocation_sums(one, "20000.00")

    def test_allocation_good_month(self):
        self.seed_trailing_months(("10000.00", "10000.00", "10000.00"))
        result = recommend_allocation(self.user, Decimal("12000.00"), reference_date=self.today)
        self.assertEqual(result["classification"], CLASSIFICATION_GOOD)
        self.assertFalse(result["used_default_average"])
        self.assertEqual(result["allocation"]["reinvestment"], Decimal("4800.00"))
        self.assertEqual(result["allocation"]["personal"], Decimal("3000.00"))
        self.assertEqual(result["allocation"]["emergency"], Decimal("1800.00"))
        self.assertEqual(result["allocation"]["goals"], Decimal("2400.00"))
        self.assert_allocation_sums(result, "12000.00")

    def test_allocation_average_month(self):
        self.seed_trailing_months(("10000.00", "10000.00", "10000.00"))
        at_floor = recommend_allocation(self.user, Decimal("8000.00"), reference_date=self.today)
        mid = recommend_allocation(self.user, Decimal("10000.00"), reference_date=self.today)
        just_under_good = recommend_allocation(
            self.user, Decimal("11999.99"), reference_date=self.today
        )
        self.assertEqual(at_floor["classification"], CLASSIFICATION_AVERAGE)
        self.assertEqual(mid["classification"], CLASSIFICATION_AVERAGE)
        self.assertEqual(just_under_good["classification"], CLASSIFICATION_AVERAGE)
        self.assert_allocation_sums(at_floor, "8000.00")
        self.assert_allocation_sums(mid, "10000.00")
        self.assert_allocation_sums(just_under_good, "11999.99")

    def test_allocation_bad_month(self):
        self.seed_trailing_months(("10000.00", "10000.00", "10000.00"))
        result = recommend_allocation(self.user, Decimal("7999.99"), reference_date=self.today)
        self.assertEqual(result["classification"], CLASSIFICATION_BAD)
        self.assertEqual(result["allocation"]["reinvestment"], Decimal("2000.00"))
        self.assertEqual(result["allocation"]["personal"], Decimal("3200.00"))
        self.assertEqual(result["allocation"]["emergency"], Decimal("1600.00"))
        self.assertEqual(result["allocation"]["goals"], Decimal("1199.99"))
        self.assert_allocation_sums(result, "7999.99")

    def test_allocation_rounding_absorbed_by_last_category(self):
        self.seed_trailing_months(("10000.00", "10000.00", "10000.00"))
        for amount in ("100.01", "33.33", "1.00", "999.99"):
            result = recommend_allocation(self.user, Decimal(amount), reference_date=self.today)
            self.assert_allocation_sums(result, amount)
            self.assertEqual(set(result["allocation"]), set(ALLOCATION_CATEGORIES))
            splits = ALLOCATION_SPLITS[result["classification"]]
            first_three = sum(
                (result["allocation"][name] for name in ALLOCATION_CATEGORIES[:-1]),
                Decimal("0.00"),
            )
            expected_last = Decimal(amount) - first_three
            self.assertEqual(result["allocation"]["goals"], expected_last)
            self.assertEqual(sum(splits.values()), Decimal("1.00"))


class PlanningAPITests(APITestCase):
    available_url = reverse("planning-available-money")
    afford_url = reverse("planning-can-i-afford")
    allocate_url = reverse("planning-allocate")

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+256700777002",
            password="SecurePass123!",
            full_name="API Planner",
        )
        self.today = timezone.localdate()
        Transaction.objects.create(
            user=self.user,
            type="income",
            amount=Decimal("100000.00"),
            category="sales",
            date=self.today,
        )
        Transaction.objects.create(
            user=self.user,
            type="expense",
            amount=Decimal("20000.00"),
            category="rent",
            date=self.today,
        )
        UpcomingExpense.objects.create(
            user=self.user,
            description="Stock",
            amount=Decimal("10000.00"),
            expected_date=self.today + timedelta(days=7),
        )

    def authenticate(self):
        response = self.client.post(
            reverse("auth-login"),
            {"phone_number": self.user.phone_number, "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_available_money_returns_breakdown(self):
        self.authenticate()
        response = self.client.get(self.available_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["safely_available_amount"], "65000.00")
        self.assertEqual(response.data["cash_on_hand"], "80000.00")
        self.assertEqual(response.data["upcoming_expenses"], "10000.00")
        self.assertEqual(response.data["emergency_reserve"], "5000.00")
        self.assertGreaterEqual(Decimal(response.data["safely_available_amount"]), Decimal("0"))

    def test_can_i_afford_returns_status_and_explanation(self):
        self.authenticate()
        green = self.client.post(self.afford_url, {"amount": "65000.00"}, format="json")
        yellow = self.client.post(self.afford_url, {"amount": "78000.00"}, format="json")
        red = self.client.post(self.afford_url, {"amount": "78000.01"}, format="json")
        self.assertEqual(green.data["status"], STATUS_GREEN)
        self.assertEqual(yellow.data["status"], STATUS_YELLOW)
        self.assertEqual(red.data["status"], STATUS_RED)
        self.assertTrue(green.data["explanation"])
        self.assertTrue(yellow.data["explanation"])
        self.assertTrue(red.data["explanation"])

    def test_allocate_returns_average_split_without_history(self):
        self.authenticate()
        response = self.client.post(self.allocate_url, {"amount": "100.01"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["classification"], CLASSIFICATION_AVERAGE)
        self.assertTrue(response.data["used_default_average"])
        allocation = response.data["allocation"]
        total = sum(Decimal(allocation[name]) for name in ALLOCATION_CATEGORIES)
        self.assertEqual(total, Decimal("100.01"))
        self.assertTrue(response.data["explanation"])
