from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import BusinessProfile, BusinessType, Language, TrackingFrequency, User
from apps.commitments.models import Commitment, CommitmentStatus
from apps.goals.models import Goal, GoalStatus
from apps.planning.decision_engine import assess_affordability
from apps.retirement.models import RetirementProfile
from apps.retirement.projection import calculate_retirement_projection
from apps.sms_gateway.client import send_sms
from apps.sms_gateway.commands import handle_incoming_sms, parse_command, sms_label
from apps.sms_gateway.models import RegistrationSession, RegistrationStep
from apps.sms_gateway.registration import business_type_options
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

    def test_goal_and_retire_aliases(self):
        self.assertEqual(parse_command("GOAL"), ("goal", {}))
        self.assertEqual(parse_command("goal"), ("goal", {}))
        self.assertEqual(parse_command("RETIRE"), ("retire", {}))
        self.assertEqual(parse_command("retirement"), ("retire", {}))

    def test_confirm_requires_amount(self):
        self.assertEqual(parse_command("CONFIRM 100000"), ("confirm", {"amount": "100000"}))
        self.assertEqual(parse_command("confirm 100000"), ("confirm", {"amount": "100000"}))
        self.assertEqual(parse_command("CONFIRM"), ("help", {}))

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

    def test_register_from_existing_user_does_not_start_session(self):
        reply = handle_incoming_sms(self.user.phone_number, "REGISTER")
        self.assertEqual(reply, sms_label("english", "sms_already_registered"))
        self.assertFalse(RegistrationSession.objects.filter(phone_number=self.user.phone_number).exists())
        self.assertEqual(User.objects.filter(phone_number=self.user.phone_number).count(), 1)

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

    def test_goal_reports_most_recent_active_goal(self):
        Goal.objects.create(
            user=self.user,
            name="Older stove",
            goal_type="personal",
            target_amount=Decimal("100000.00"),
            current_saved_amount=Decimal("20000.00"),
        )
        Goal.objects.create(
            user=self.user,
            name="New fridge",
            goal_type="personal",
            target_amount=Decimal("200000.00"),
            current_saved_amount=Decimal("90000.00"),
        )
        Goal.objects.create(
            user=self.user,
            name="Finished cart",
            goal_type="business_growth",
            target_amount=Decimal("50000.00"),
            current_saved_amount=Decimal("50000.00"),
            status=GoalStatus.COMPLETED,
        )
        reply = handle_incoming_sms(self.user.phone_number, "GOAL")
        self.assertEqual(
            reply,
            sms_label(
                "english",
                "sms_goal_ok",
                name="New fridge",
                percent="45",
                saved="90000.00",
                target="200000.00",
            ),
        )

    def test_goal_without_active_goal_suggests_app(self):
        Goal.objects.create(
            user=self.user,
            name="Finished cart",
            goal_type="personal",
            target_amount=Decimal("50000.00"),
            current_saved_amount=Decimal("50000.00"),
            status=GoalStatus.COMPLETED,
        )
        reply = handle_incoming_sms(self.user.phone_number, "GOAL")
        self.assertEqual(reply, sms_label("english", "sms_goal_none"))

    def test_retire_on_track_uses_projection_service(self):
        profile = RetirementProfile.objects.create(
            user=self.user,
            current_age=40,
            desired_retirement_age=41,
            current_savings=Decimal("0.00"),
            existing_pension_balance=Decimal("0.00"),
            desired_retirement_fund=Decimal("120000.00"),
            current_monthly_contribution=Decimal("10000.00"),
        )
        expected = calculate_retirement_projection(profile)
        self.assertTrue(expected["on_track"])
        reply = handle_incoming_sms(self.user.phone_number, "RETIRE")
        self.assertEqual(
            reply,
            sms_label(
                "english",
                "sms_retire_on_track",
                amount=f"{expected['required_monthly_contribution']:.2f}",
            ),
        )
        self.assertIn("estimate", reply.lower())

    def test_retirement_alias_needs_attention(self):
        profile = RetirementProfile.objects.create(
            user=self.user,
            current_age=30,
            desired_retirement_age=32,
            current_savings=Decimal("10000.00"),
            existing_pension_balance=Decimal("5000.00"),
            desired_retirement_fund=Decimal("50000.00"),
            current_monthly_contribution=Decimal("1000.00"),
        )
        expected = calculate_retirement_projection(profile)
        self.assertFalse(expected["on_track"])
        reply = handle_incoming_sms(self.user.phone_number, "RETIREMENT")
        self.assertEqual(
            reply,
            sms_label(
                "english",
                "sms_retire_needs_attention",
                amount=f"{expected['required_monthly_contribution']:.2f}",
            ),
        )

    def test_retire_without_profile_suggests_app(self):
        reply = handle_incoming_sms(self.user.phone_number, "RETIRE")
        self.assertEqual(reply, sms_label("english", "sms_retire_none"))

    def test_confirm_marks_fulfilled_like_apply_confirmation(self):
        commitment = Commitment.objects.create(
            user=self.user,
            target_amount=Decimal("100000.00"),
            period_start=self.today - timedelta(days=7),
            period_end=self.today - timedelta(days=1),
        )
        reply = handle_incoming_sms(self.user.phone_number, "CONFIRM 100000")
        commitment.refresh_from_db()
        self.assertEqual(commitment.status, CommitmentStatus.FULFILLED)
        self.assertEqual(commitment.saved_amount, Decimal("100000.00"))
        self.assertEqual(
            reply,
            sms_label(
                "english",
                "sms_confirm_ok",
                amount="100000.00",
                result="Fulfilled",
                status=CommitmentStatus.FULFILLED,
            ),
        )

    def test_confirm_marks_partial_on_oldest_pending(self):
        older = Commitment.objects.create(
            user=self.user,
            target_amount=Decimal("100000.00"),
            period_start=self.today - timedelta(days=14),
            period_end=self.today - timedelta(days=8),
        )
        newer = Commitment.objects.create(
            user=self.user,
            target_amount=Decimal("50000.00"),
            period_start=self.today - timedelta(days=7),
            period_end=self.today - timedelta(days=1),
        )
        reply = handle_incoming_sms(self.user.phone_number, "CONFIRM 40000")
        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(older.status, CommitmentStatus.PARTIAL)
        self.assertEqual(older.saved_amount, Decimal("40000.00"))
        self.assertEqual(newer.status, CommitmentStatus.PENDING)
        self.assertEqual(newer.saved_amount, Decimal("0.00"))
        self.assertEqual(
            reply,
            sms_label(
                "english",
                "sms_confirm_ok",
                amount="40000.00",
                result="Partial",
                status=CommitmentStatus.PARTIAL,
            ),
        )

    def test_confirm_without_pending_commitment(self):
        reply = handle_incoming_sms(self.user.phone_number, "CONFIRM 100000")
        self.assertEqual(reply, sms_label("english", "sms_confirm_none"))
        self.assertEqual(Commitment.objects.count(), 0)


class SMSRegistrationFlowTests(TestCase):
    phone = "+256700999001"

    def test_full_registration_creates_user_and_unlocks_commands(self):
        welcome = handle_incoming_sms(self.phone, "register")
        self.assertEqual(welcome, sms_label("english", "sms_register_welcome"))
        session = RegistrationSession.objects.get(phone_number=self.phone)
        self.assertEqual(session.current_step, RegistrationStep.AWAITING_NAME)

        asked_business = handle_incoming_sms(self.phone, "Amina Nalwoga")
        self.assertEqual(
            asked_business,
            sms_label("english", "sms_register_ask_business", name="Amina Nalwoga"),
        )
        session.refresh_from_db()
        self.assertEqual(session.current_step, RegistrationStep.AWAITING_BUSINESS_NAME)
        self.assertEqual(session.collected_full_name, "Amina Nalwoga")

        asked_type = handle_incoming_sms(self.phone, "Amina Stall")
        self.assertEqual(
            asked_type,
            sms_label("english", "sms_register_ask_type", options=business_type_options()),
        )
        session.refresh_from_db()
        self.assertEqual(session.current_step, RegistrationStep.AWAITING_BUSINESS_TYPE)
        self.assertEqual(session.collected_business_name, "Amina Stall")

        asked_frequency = handle_incoming_sms(self.phone, "8")
        self.assertEqual(asked_frequency, sms_label("english", "sms_register_ask_frequency"))
        session.refresh_from_db()
        self.assertEqual(session.current_step, RegistrationStep.AWAITING_TRACKING_FREQUENCY)
        self.assertEqual(session.collected_business_type, BusinessType.TRADER)

        done = handle_incoming_sms(self.phone, "2")
        self.assertEqual(done, sms_label("english", "sms_register_done", name="Amina Nalwoga"))
        session.refresh_from_db()
        self.assertEqual(session.current_step, RegistrationStep.COMPLETE)

        user = User.objects.get(phone_number=self.phone)
        self.assertEqual(user.full_name, "Amina Nalwoga")
        self.assertEqual(user.preferred_language, Language.ENGLISH)
        self.assertFalse(user.has_usable_password())
        profile = user.business_profile
        self.assertEqual(profile.business_name, "Amina Stall")
        self.assertEqual(profile.business_type, BusinessType.TRADER)
        self.assertEqual(profile.tracking_frequency, TrackingFrequency.WEEKLY)

        income = handle_incoming_sms(self.phone, "INCOME 50000 SALES")
        self.assertEqual(
            income,
            sms_label("english", "sms_income_ok", amount="50000.00", category="SALES"),
        )
        self.assertEqual(Transaction.objects.filter(user=user).count(), 1)
        balance = handle_incoming_sms(self.phone, "BAL")
        self.assertIn("50000.00", balance)

    def test_invalid_business_type_is_reasked(self):
        handle_incoming_sms(self.phone, "REGISTER")
        handle_incoming_sms(self.phone, "Amina Nalwoga")
        handle_incoming_sms(self.phone, "Amina Stall")
        reply = handle_incoming_sms(self.phone, "99")
        self.assertEqual(
            reply,
            sms_label("english", "sms_register_invalid_type", options=business_type_options()),
        )
        session = RegistrationSession.objects.get(phone_number=self.phone)
        self.assertEqual(session.current_step, RegistrationStep.AWAITING_BUSINESS_TYPE)
        self.assertEqual(session.collected_business_type, "")
        self.assertFalse(User.objects.filter(phone_number=self.phone).exists())

        next_reply = handle_incoming_sms(self.phone, "8")
        self.assertEqual(next_reply, sms_label("english", "sms_register_ask_frequency"))
        session.refresh_from_db()
        self.assertEqual(session.collected_business_type, BusinessType.TRADER)

    def test_invalid_tracking_frequency_is_reasked(self):
        handle_incoming_sms(self.phone, "REGISTER")
        handle_incoming_sms(self.phone, "Amina Nalwoga")
        handle_incoming_sms(self.phone, "Amina Stall")
        handle_incoming_sms(self.phone, "8")
        reply = handle_incoming_sms(self.phone, "9")
        self.assertEqual(reply, sms_label("english", "sms_register_invalid_frequency"))
        session = RegistrationSession.objects.get(phone_number=self.phone)
        self.assertEqual(session.current_step, RegistrationStep.AWAITING_TRACKING_FREQUENCY)
        self.assertEqual(session.collected_tracking_frequency, "")
        self.assertFalse(User.objects.filter(phone_number=self.phone).exists())

        done = handle_incoming_sms(self.phone, "1")
        self.assertEqual(done, sms_label("english", "sms_register_done", name="Amina Nalwoga"))
        user = User.objects.get(phone_number=self.phone)
        self.assertEqual(user.business_profile.tracking_frequency, TrackingFrequency.DAILY)

    def test_stale_session_is_discarded_on_new_register(self):
        handle_incoming_sms(self.phone, "REGISTER")
        handle_incoming_sms(self.phone, "Old Name")
        session = RegistrationSession.objects.get(phone_number=self.phone)
        RegistrationSession.objects.filter(pk=session.pk).update(
            updated_at=timezone.now() - timedelta(minutes=31),
        )

        reply = handle_incoming_sms(self.phone, "REGISTER")
        self.assertEqual(reply, sms_label("english", "sms_register_welcome"))
        session.refresh_from_db()
        self.assertEqual(session.current_step, RegistrationStep.AWAITING_NAME)
        self.assertEqual(session.collected_full_name, "")
        self.assertFalse(User.objects.filter(phone_number=self.phone).exists())


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
