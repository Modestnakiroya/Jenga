from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import BusinessProfile, Language, User
from apps.planning.decision_engine import assess_affordability
from apps.sms_gateway.client import send_sms
from apps.sms_gateway.commands import handle_incoming_sms, parse_command, sms_label
from apps.transactions.models import Transaction
from apps.transactions.serializers import TransactionSerializer
from apps.transactions.services import calculate_financial_summary


class CommandParserTests(SimpleTestCase):
    def test_income_is_case_insensitive(self):
        self.assertEqual(
            parse_command("income 50000 sales"),
            ("income", {"amount": "50000", "category": "sales"}),
        )
        self.assertEqual(
            parse_command("InCoMe 50000 SALES"),
            ("income", {"amount": "50000", "category": "sales"}),
        )

    def test_expense_joins_multi_word_category(self):
        self.assertEqual(
            parse_command("EXPENSE 20000 RENT"),
            ("expense", {"amount": "20000", "category": "rent"}),
        )
        self.assertEqual(
            parse_command("expense 15000 stock inventory"),
            ("expense", {"amount": "15000", "category": "stock_inventory"}),
        )

    def test_balance_aliases(self):
        self.assertEqual(parse_command("BALANCE"), ("balance", {}))
        self.assertEqual(parse_command("bal"), ("balance", {}))

    def test_can_i_afford_is_case_insensitive(self):
        self.assertEqual(
            parse_command("caniafford 300000"),
            ("can_afford", {"amount": "300000"}),
        )
        self.assertEqual(
            parse_command("CANIAFFORD 300000"),
            ("can_afford", {"amount": "300000"}),
        )

    def test_unrecognized_command_returns_help(self):
        self.assertEqual(parse_command("HELLO"), ("help", {}))
        self.assertEqual(parse_command("INCOME 50000"), ("help", {}))
        self.assertEqual(parse_command("CANIAFFORD"), ("help", {}))
        self.assertEqual(parse_command(""), ("help", {}))


class IncomingSMSCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+256700123001",
            password="SecurePass123!",
            full_name="SMS User",
        )
        BusinessProfile.objects.create(
            user=self.user,
            business_name="SMS Stall",
            business_type="trader",
            tracking_frequency="weekly",
        )
        self.today = timezone.localdate()

    def test_unregistered_phone_does_not_lookup_or_write(self):
        reply = handle_incoming_sms("+256700000000", "INCOME 50000 SALES")
        self.assertEqual(reply, sms_label("english", "sms_register_first"))
        self.assertEqual(Transaction.objects.count(), 0)

    def test_unregistered_invalid_phone_is_handled(self):
        reply = handle_incoming_sms("not-a-phone", "BAL")
        self.assertEqual(reply, sms_label("english", "sms_register_first"))
        self.assertEqual(Transaction.objects.count(), 0)

    def test_unrecognized_command_returns_help_message(self):
        reply = handle_incoming_sms(self.user.phone_number, "WHAT")
        self.assertEqual(reply, sms_label("english", "sms_help"))
        self.assertEqual(Transaction.objects.count(), 0)

    def test_income_creates_transaction_like_the_api_serializer(self):
        reply = handle_incoming_sms(self.user.phone_number, "INCOME 50000 SALES")
        tx = Transaction.objects.get(user=self.user)
        expected = TransactionSerializer(
            data={"type": "income", "amount": "50000", "category": "sales"}
        )
        self.assertTrue(expected.is_valid(), expected.errors)
        self.assertEqual(tx.type, "income")
        self.assertEqual(tx.amount, Decimal("50000.00"))
        self.assertEqual(tx.category, "sales")
        self.assertEqual(tx.date, self.today)
        self.assertEqual(tx.description, "")
        self.assertEqual(
            reply,
            sms_label("english", "sms_income_ok", amount="50000.00", category="SALES"),
        )

    def test_expense_creates_transaction_like_the_api_serializer(self):
        reply = handle_incoming_sms(self.user.phone_number, "expense 20000 rent")
        tx = Transaction.objects.get(user=self.user)
        self.assertEqual(tx.type, "expense")
        self.assertEqual(tx.amount, Decimal("20000.00"))
        self.assertEqual(tx.category, "rent")
        self.assertEqual(tx.date, self.today)
        self.assertEqual(
            reply,
            sms_label("english", "sms_expense_ok", amount="20000.00", category="RENT"),
        )

    def test_balance_matches_summary_service(self):
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
            amount=Decimal("25000.00"),
            category="rent",
            date=self.today,
        )
        expected = calculate_financial_summary(self.user, "weekly", self.today)
        reply = handle_incoming_sms(self.user.phone_number, "BAL")
        self.assertEqual(
            reply,
            sms_label(
                "english",
                "sms_balance",
                income=f"{expected['total_income']:.2f}",
                expenses=f"{expected['total_expenses']:.2f}",
                profit=f"{expected['estimated_profit']:.2f}",
            ),
        )

    def test_can_i_afford_matches_decision_engine(self):
        Transaction.objects.create(
            user=self.user,
            type="income",
            amount=Decimal("400000.00"),
            category="sales",
            date=self.today,
        )
        expected = assess_affordability(self.user, Decimal("300000.00"))
        reply = handle_incoming_sms(self.user.phone_number, "CANIAFFORD 300000")
        self.assertEqual(
            reply,
            sms_label(
                "english",
                "sms_can_afford",
                status=expected["status"],
                safe=f"{expected['safely_available_amount']:.2f}",
                amount=f"{expected['requested_amount']:.2f}",
            ),
        )
        self.assertIn(expected["status"], reply)

    def test_replies_use_preferred_language_templates(self):
        self.user.preferred_language = Language.LUGANDA
        self.user.save(update_fields=["preferred_language"])
        reply = handle_incoming_sms(self.user.phone_number, "INCOME 50000 SALES")
        expected = sms_label("luganda", "sms_income_ok", amount="50000.00", category="SALES")
        self.assertEqual(reply, expected)
        self.assertNotEqual(expected, sms_label("english", "sms_income_ok", amount="50000.00", category="SALES"))
        self.assertEqual(Transaction.objects.get().category, "sales")


class IncomingSMSWebhookTests(APITestCase):
    url = reverse("sms-incoming")

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+256700123002",
            password="SecurePass123!",
            full_name="Webhook User",
        )
        BusinessProfile.objects.create(
            user=self.user,
            business_name="Webhook Stall",
            business_type="trader",
            tracking_frequency="weekly",
        )

    def test_empty_payload_is_rejected(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Transaction.objects.count(), 0)

    @patch("apps.sms_gateway.views.send_sms")
    def test_africa_talking_form_post_records_income(self, mock_send):
        response = self.client.post(
            self.url,
            {"from": self.user.phone_number, "text": "INCOME 50000 SALES"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.args[0], self.user.phone_number)
        self.assertIn("50000.00", mock_send.call_args.args[1])

    @patch("apps.sms_gateway.views.send_sms")
    def test_unregistered_sender_gets_register_message(self, mock_send):
        response = self.client.post(
            self.url,
            {"from": "+256700000099", "text": "BAL"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Transaction.objects.count(), 0)
        mock_send.assert_called_once_with(
            "+256700000099",
            sms_label("english", "sms_register_first"),
        )


class SendSMSClientTests(SimpleTestCase):
    @patch("apps.sms_gateway.client.africastalking")
    @patch.dict("os.environ", {"AT_USERNAME": "sandbox", "AT_API_KEY": "test-key"}, clear=False)
    def test_send_sms_initializes_sdk(self, mock_at):
        mock_at.SMS.send.return_value = {"SMSMessageData": {"Recipients": []}}
        result = send_sms("+256700123001", "hello")
        mock_at.initialize.assert_called_once_with("sandbox", "test-key")
        mock_at.SMS.send.assert_called_once_with("hello", ["+256700123001"])
        self.assertEqual(result, {"SMSMessageData": {"Recipients": []}})

    @patch("apps.sms_gateway.client.africastalking")
    @patch.dict("os.environ", {"AT_USERNAME": "sandbox", "AT_API_KEY": "test-key"}, clear=False)
    def test_send_sms_adds_plus_when_africa_talking_omits_it(self, mock_at):
        mock_at.SMS.send.return_value = {"SMSMessageData": {"Recipients": []}}
        send_sms("256700123001", "hello")
        mock_at.SMS.send.assert_called_once_with("hello", ["+256700123001"])

    @patch("apps.sms_gateway.client.africastalking")
    @patch.dict("os.environ", {"AT_USERNAME": "", "AT_API_KEY": ""}, clear=False)
    def test_missing_credentials_are_logged_not_raised(self, mock_at):
        self.assertIsNone(send_sms("+256700123001", "hello"))
        mock_at.initialize.assert_not_called()
        mock_at.SMS.send.assert_not_called()

    @patch("apps.sms_gateway.client.africastalking")
    @patch.dict("os.environ", {"AT_USERNAME": "sandbox", "AT_API_KEY": "test-key"}, clear=False)
    def test_sdk_failure_is_logged_not_raised(self, mock_at):
        mock_at.SMS.send.side_effect = RuntimeError("network")
        self.assertIsNone(send_sms("+256700123001", "hello"))
        mock_at.initialize.assert_called_once()
