from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import BusinessProfile, User
from apps.transactions.models import Transaction
from apps.transactions.services import calculate_financial_summary, period_bounds


class TransactionAPITests(APITestCase):
    list_url = reverse("transaction-list")

    def setUp(self):
        self.user_a = User.objects.create_user(
            phone_number="+256700111111",
            password="SecurePass123!",
            full_name="User A",
        )
        self.user_b = User.objects.create_user(
            phone_number="+256700222222",
            password="SecurePass123!",
            full_name="User B",
        )

    def authenticate(self, user, password="SecurePass123!"):
        response = self.client.post(
            reverse("auth-login"),
            {"phone_number": user.phone_number, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response

    def create_transaction(self, **overrides):
        payload = {
            "type": "income",
            "amount": "85000.00",
            "category": "sales",
            "description": "Market sales",
            "date": timezone.localdate().isoformat(),
        }
        payload.update(overrides)
        return self.client.post(self.list_url, payload, format="json")

    def test_create_income_transaction(self):
        self.authenticate(self.user_a)
        response = self.create_transaction()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "income")
        self.assertEqual(Decimal(response.data["amount"]), Decimal("85000.00"))
        self.assertEqual(response.data["category"], "sales")
        self.assertEqual(Transaction.objects.filter(user=self.user_a).count(), 1)

    def test_create_expense_transaction(self):
        self.authenticate(self.user_a)
        response = self.create_transaction(
            type="expense",
            amount="12000.00",
            category="transport",
            description="boda",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "expense")
        self.assertEqual(response.data["category"], "transport")
        self.assertEqual(Transaction.objects.get().user, self.user_a)

    def test_ownership_isolation(self):
        self.authenticate(self.user_a)
        created = self.create_transaction()
        tx_id = created.data["id"]
        detail_url = reverse("transaction-detail", args=[tx_id])

        self.authenticate(self.user_b)
        listed = self.client.get(self.list_url)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(listed.data, [])

        detail = self.client.get(detail_url)
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

        patched = self.client.patch(detail_url, {"description": "stolen"}, format="json")
        self.assertEqual(patched.status_code, status.HTTP_404_NOT_FOUND)

        deleted = self.client.delete(detail_url)
        self.assertEqual(deleted.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Transaction.objects.filter(id=tx_id, user=self.user_a).exists())

    def test_date_range_filtering(self):
        self.authenticate(self.user_a)
        today = timezone.localdate()
        Transaction.objects.create(
            user=self.user_a,
            type="income",
            amount=Decimal("10000.00"),
            category="sales",
            date=today - timedelta(days=10),
        )
        Transaction.objects.create(
            user=self.user_a,
            type="income",
            amount=Decimal("20000.00"),
            category="sales",
            date=today - timedelta(days=2),
        )
        Transaction.objects.create(
            user=self.user_a,
            type="expense",
            amount=Decimal("3000.00"),
            category="rent",
            date=today,
        )

        start = (today - timedelta(days=3)).isoformat()
        end = today.isoformat()
        response = self.client.get(self.list_url, {"start_date": start, "end_date": end})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dates = {item["date"] for item in response.data}
        self.assertEqual(dates, {(today - timedelta(days=2)).isoformat(), today.isoformat()})

    def test_future_date_rejected(self):
        self.authenticate(self.user_a)
        future = (timezone.localdate() + timedelta(days=1)).isoformat()
        response = self.create_transaction(date=future)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("date", response.data)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_mismatched_category_type_rejected(self):
        self.authenticate(self.user_a)
        income_with_rent = self.create_transaction(type="income", category="rent")
        expense_with_sales = self.create_transaction(
            type="expense",
            category="sales",
            amount="5000.00",
        )

        self.assertEqual(income_with_rent.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", income_with_rent.data)
        self.assertEqual(expense_with_sales.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", expense_with_sales.data)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_zero_and_negative_amounts_rejected(self):
        self.authenticate(self.user_a)
        zero = self.create_transaction(amount="0")
        negative = self.create_transaction(amount="-10.00")

        self.assertEqual(zero.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", zero.data)
        self.assertEqual(negative.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", negative.data)
        self.assertEqual(Transaction.objects.count(), 0)


class FinancialSummaryTests(APITestCase):
    summary_url = reverse("financial-summary")
    # Saturday 5 Sep 2026: week is Mon 31 Aug – Sun 6 Sep.
    reference = date(2026, 9, 5)

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+256700444001",
            password="SecurePass123!",
            full_name="Summary User",
        )
        self.other = User.objects.create_user(
            phone_number="+256700444002",
            password="SecurePass123!",
            full_name="Other User",
        )
        BusinessProfile.objects.create(
            user=self.user,
            business_name="Summary Stall",
            business_type="market_vendor",
            tracking_frequency="weekly",
        )

    def authenticate(self, user=None):
        user = user or self.user
        response = self.client.post(
            reverse("auth-login"),
            {"phone_number": user.phone_number, "password": "SecurePass123!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def seed(self, user, tx_type, amount, tx_date, category=None):
        if category is None:
            category = "sales" if tx_type == "income" else "rent"
        return Transaction.objects.create(
            user=user,
            type=tx_type,
            amount=Decimal(amount),
            category=category,
            date=tx_date,
        )

    def test_daily_aggregation_matches_manual_total(self):
        self.seed(self.user, "income", "10000.00", self.reference)
        self.seed(self.user, "income", "5000.00", self.reference)
        self.seed(self.user, "expense", "3000.00", self.reference)
        self.seed(self.user, "income", "9999.00", self.reference - timedelta(days=1))
        self.seed(self.other, "income", "8000.00", self.reference)

        expected_income = Decimal("15000.00")
        expected_expenses = Decimal("3000.00")
        summary = calculate_financial_summary(self.user, "daily", self.reference)

        self.assertEqual(summary["period_start"], self.reference)
        self.assertEqual(summary["period_end"], self.reference)
        self.assertEqual(summary["total_income"], expected_income)
        self.assertEqual(summary["total_expenses"], expected_expenses)
        self.assertEqual(summary["estimated_profit"], expected_income - expected_expenses)
        self.assertEqual(summary["transaction_count"], 3)

        self.authenticate()
        response = self.client.get(
            self.summary_url,
            {"period": "daily", "date": self.reference.isoformat()},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_income"], "15000.00")
        self.assertEqual(response.data["total_expenses"], "3000.00")
        self.assertEqual(response.data["estimated_profit"], "12000.00")
        self.assertEqual(response.data["transaction_count"], 3)

    def test_weekly_aggregation_monday_to_sunday(self):
        start, end = period_bounds("weekly", self.reference)
        self.assertEqual(start, date(2026, 8, 31))
        self.assertEqual(end, date(2026, 9, 6))

        self.seed(self.user, "income", "20000.00", date(2026, 8, 31))
        self.seed(self.user, "expense", "4000.00", date(2026, 9, 3))
        self.seed(self.user, "income", "7000.00", date(2026, 9, 6))
        self.seed(self.user, "income", "1000.00", date(2026, 8, 30))
        self.seed(self.user, "expense", "1000.00", date(2026, 9, 7))

        expected_income = Decimal("27000.00")
        expected_expenses = Decimal("4000.00")
        summary = calculate_financial_summary(self.user, "weekly", self.reference)

        self.assertEqual(summary["period_start"], start)
        self.assertEqual(summary["period_end"], end)
        self.assertEqual(summary["total_income"], expected_income)
        self.assertEqual(summary["total_expenses"], expected_expenses)
        self.assertEqual(summary["estimated_profit"], Decimal("23000.00"))
        self.assertEqual(summary["transaction_count"], 3)

    def test_monthly_aggregation_first_to_last_day(self):
        start, end = period_bounds("monthly", self.reference)
        self.assertEqual(start, date(2026, 9, 1))
        self.assertEqual(end, date(2026, 9, 30))

        self.seed(self.user, "income", "50000.00", date(2026, 9, 1))
        self.seed(self.user, "expense", "12000.00", date(2026, 9, 30))
        self.seed(self.user, "income", "8000.00", date(2026, 8, 31))
        self.seed(self.user, "expense", "2000.00", date(2026, 10, 1))

        expected_income = Decimal("50000.00")
        expected_expenses = Decimal("12000.00")
        summary = calculate_financial_summary(self.user, "monthly", self.reference)

        self.assertEqual(summary["total_income"], expected_income)
        self.assertEqual(summary["total_expenses"], expected_expenses)
        self.assertEqual(summary["estimated_profit"], Decimal("38000.00"))
        self.assertEqual(summary["transaction_count"], 2)

    def test_defaults_to_tracking_frequency_and_today(self):
        self.user.business_profile.tracking_frequency = "monthly"
        self.user.business_profile.save()
        today = timezone.localdate()
        self.seed(self.user, "income", "11000.00", today.replace(day=1))
        self.seed(self.user, "expense", "1000.00", today)

        self.authenticate()
        response = self.client.get(self.summary_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["period"], "monthly")
        month_start, month_end = period_bounds("monthly", today)
        self.assertEqual(response.data["period_start"], month_start.isoformat())
        self.assertEqual(response.data["period_end"], month_end.isoformat())
        self.assertEqual(response.data["total_income"], "11000.00")
        self.assertEqual(response.data["total_expenses"], "1000.00")
        self.assertEqual(response.data["estimated_profit"], "10000.00")

    def test_empty_period_returns_zeros(self):
        summary = calculate_financial_summary(self.user, "daily", self.reference)
        self.assertEqual(summary["total_income"], Decimal("0.00"))
        self.assertEqual(summary["total_expenses"], Decimal("0.00"))
        self.assertEqual(summary["estimated_profit"], Decimal("0.00"))
        self.assertEqual(summary["transaction_count"], 0)

        self.authenticate()
        response = self.client.get(
            self.summary_url,
            {"period": "daily", "date": self.reference.isoformat()},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_income"], "0.00")
        self.assertEqual(response.data["total_expenses"], "0.00")
        self.assertEqual(response.data["estimated_profit"], "0.00")
        self.assertEqual(response.data["transaction_count"], 0)
