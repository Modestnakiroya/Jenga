import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.assistant.llm import LLMError, call_llm
from apps.assistant.sunbird_client import LANGUAGE_CODES, translate_text
from apps.assistant.translations import DASHBOARD_LABELS, ENGLISH_LABELS, SUPPORTED_LANGUAGES

from apps.accounts.models import BusinessProfile, User
from apps.assistant.engine import (
    INTENT_CAN_I_AFFORD,
    INTENT_CHECK_SUMMARY,
    INTENT_GENERAL_QUESTION,
    INTENT_HOW_MUCH_SAVE,
    INTENT_RECORD_TRANSACTION,
    INTENT_RETIREMENT_CHECK,
)
from apps.assistant.prompts import (
    HYPOTHETICAL_ALLOCATION_DISCLAIMER,
    LOW_CONFIDENCE_REPLY,
    NO_GOAL_REPLY,
    NO_RETIREMENT_REPLY,
    NO_TRANSACTIONS_REPLY,
    PERSONAL_GENERAL_REPLY,
)
from apps.assistant.prompts import PHRASE_SYSTEM, LITERACY_SYSTEM
from apps.goals.models import Goal
from apps.planning.decision_engine import assess_affordability, recommend_allocation
from apps.planning.models import UpcomingExpense
from apps.retirement.models import RetirementProfile
from apps.retirement.projection import PROJECTION_DISCLAIMER, calculate_retirement_projection
from apps.transactions.models import Transaction
from apps.transactions.services import calculate_financial_summary


def classify(intent, confidence=0.95, **parameters):
    return json.dumps(
        {
            "intent": intent,
            "confidence": confidence,
            "parameters": parameters,
        }
    )


class AssistantAskTests(APITestCase):
    ask_url = reverse("assistant-ask")

    def setUp(self):
        self.today = timezone.localdate()
        self.user = User.objects.create_user(
            phone_number="+256700999001",
            password="SecurePass123!",
            full_name="Asker",
        )
        BusinessProfile.objects.create(
            user=self.user,
            business_name="Ask Stall",
            business_type="trader",
            tracking_frequency="weekly",
        )

    def authenticate(self):
        response = self.client.post(
            reverse("auth-login"),
            {"phone_number": self.user.phone_number, "password": "SecurePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def ask(self, message="help"):
        return self.client.post(self.ask_url, {"message": message}, format="json")

    def seed_money(self):
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

    def test_response_prompts_require_plain_language(self):
        self.assertIn("Avoid technical terms", PHRASE_SYSTEM)
        self.assertIn("simple everyday language", LITERACY_SYSTEM)

    @patch("apps.assistant.views.call_llm")
    def test_record_transaction_uses_serializer_not_llm_numbers(self, mock_llm):
        self.authenticate()
        mock_llm.side_effect = [
            classify(
                INTENT_RECORD_TRANSACTION,
                type="income",
                amount="85000.00",
                category="sales",
                description="Market sales",
                date=self.today.isoformat(),
            ),
            "Recorded income of 85000.00 for sales.",
        ]
        response = self.ask("Record 85000 sales today")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["intent"], INTENT_RECORD_TRANSACTION)
        tx = Transaction.objects.get(user=self.user)
        self.assertEqual(Decimal(response.data["facts"]["amount"]), tx.amount)
        self.assertEqual(response.data["facts"]["amount"], "85000.00")
        self.assertEqual(response.data["facts"]["type"], "income")
        self.assertIn("85000.00", response.data["reply"])
        self.assertEqual(mock_llm.call_count, 2)

    @patch("apps.assistant.views.call_llm")
    def test_check_summary_matches_service(self, mock_llm):
        self.authenticate()
        self.seed_money()
        expected = calculate_financial_summary(self.user, "weekly", self.today)
        mock_llm.side_effect = [
            classify(INTENT_CHECK_SUMMARY, period="weekly"),
            "This week income is 100000.00.",
        ]
        response = self.ask("How did this week go?")
        self.assertEqual(response.data["intent"], INTENT_CHECK_SUMMARY)
        self.assertEqual(response.data["facts"]["total_income"], f"{expected['total_income']:.2f}")
        self.assertEqual(response.data["facts"]["total_expenses"], f"{expected['total_expenses']:.2f}")
        self.assertEqual(response.data["facts"]["estimated_profit"], f"{expected['estimated_profit']:.2f}")
        self.assertEqual(response.data["facts"]["transaction_count"], expected["transaction_count"])

    @patch("apps.assistant.views.call_llm")
    def test_can_i_afford_matches_planning_service(self, mock_llm):
        self.authenticate()
        self.seed_money()
        expected = assess_affordability(self.user, Decimal("65000.00"))
        mock_llm.side_effect = [
            classify(INTENT_CAN_I_AFFORD, amount="65000.00"),
            "Status GREEN for 65000.00.",
        ]
        response = self.ask("Can I afford 65000?")
        self.assertEqual(response.data["intent"], INTENT_CAN_I_AFFORD)
        self.assertEqual(response.data["facts"]["status"], expected["status"])
        self.assertEqual(
            response.data["facts"]["safely_available_amount"],
            f"{expected['safely_available_amount']:.2f}",
        )
        self.assertEqual(
            response.data["facts"]["requested_amount"],
            f"{expected['requested_amount']:.2f}",
        )

    @patch("apps.assistant.views.call_llm")
    def test_how_much_save_matches_goal_fields(self, mock_llm):
        self.authenticate()
        goal = Goal.objects.create(
            user=self.user,
            name="School fees",
            goal_type="personal",
            target_amount=Decimal("500000.00"),
            current_saved_amount=Decimal("100000.00"),
        )
        mock_llm.side_effect = [
            classify(INTENT_HOW_MUCH_SAVE, goal_name="School"),
            "You have saved 100000.00 of 500000.00.",
        ]
        response = self.ask("How much is left on school fees?")
        self.assertEqual(response.data["intent"], INTENT_HOW_MUCH_SAVE)
        self.assertEqual(response.data["facts"]["target_amount"], f"{goal.target_amount:.2f}")
        self.assertEqual(
            response.data["facts"]["current_saved_amount"],
            f"{goal.current_saved_amount:.2f}",
        )
        self.assertEqual(response.data["facts"]["progress_percentage"], f"{goal.progress_percentage:.2f}")
        self.assertEqual(response.data["facts"]["remaining_amount"], "400000.00")

    @patch("apps.assistant.views.call_llm")
    def test_retirement_check_matches_projection(self, mock_llm):
        self.authenticate()
        profile = RetirementProfile.objects.create(
            user=self.user,
            current_age=40,
            desired_retirement_age=41,
            desired_retirement_fund=Decimal("120000.00"),
            current_monthly_contribution=Decimal("10000.00"),
        )
        expected = calculate_retirement_projection(profile)
        mock_llm.side_effect = [
            classify(INTENT_RETIREMENT_CHECK),
            "Required monthly contribution is 10000.00.",
        ]
        response = self.ask("Am I on track for retirement?")
        self.assertEqual(response.data["intent"], INTENT_RETIREMENT_CHECK)
        self.assertEqual(response.data["facts"]["years_remaining"], expected["years_remaining"])
        self.assertEqual(
            response.data["facts"]["required_monthly_contribution"],
            f"{expected['required_monthly_contribution']:.2f}",
        )
        self.assertEqual(response.data["facts"]["on_track"], expected["on_track"])
        self.assertEqual(response.data["facts"]["disclaimer"], PROJECTION_DISCLAIMER)

    @patch("apps.assistant.views.call_llm")
    def test_stated_amount_without_history_uses_hypothetical_allocation(self, mock_llm):
        self.authenticate()
        expected = recommend_allocation(self.user, Decimal("200000.00"))
        mock_llm.side_effect = [
            classify(INTENT_HOW_MUCH_SAVE, amount="200000"),
            "Put 40000.00 toward goals.",
        ]
        response = self.ask("how much can I save with a weekly income of 200000")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["intent"], INTENT_HOW_MUCH_SAVE)
        self.assertTrue(response.data["facts"]["hypothetical"])
        self.assertEqual(response.data["facts"]["disclaimer"], HYPOTHETICAL_ALLOCATION_DISCLAIMER)
        self.assertEqual(response.data["facts"]["stated_amount"], "200000.00")
        self.assertEqual(
            response.data["facts"]["allocation"]["reinvestment"],
            f"{expected['allocation']['reinvestment']:.2f}",
        )
        self.assertEqual(
            response.data["facts"]["allocation"]["personal"],
            f"{expected['allocation']['personal']:.2f}",
        )
        self.assertEqual(
            response.data["facts"]["allocation"]["emergency"],
            f"{expected['allocation']['emergency']:.2f}",
        )
        self.assertEqual(
            response.data["facts"]["allocation"]["goals"],
            f"{expected['allocation']['goals']:.2f}",
        )
        self.assertIn("not your actual recorded income", response.data["reply"])
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)
        self.assertEqual(mock_llm.call_count, 2)

    @patch("apps.assistant.views.call_llm")
    def test_can_i_afford_without_history_uses_hypothetical_allocation(self, mock_llm):
        self.authenticate()
        expected = recommend_allocation(self.user, Decimal("200000.00"))
        mock_llm.side_effect = [
            classify(INTENT_CAN_I_AFFORD, amount="200000"),
            "Suggested split uses 70000.00 for reinvestment.",
        ]
        response = self.ask("can I afford to plan around a weekly income of 200000")
        self.assertEqual(response.data["intent"], INTENT_CAN_I_AFFORD)
        self.assertTrue(response.data["facts"]["hypothetical"])
        self.assertEqual(
            response.data["facts"]["allocation"]["goals"],
            f"{expected['allocation']['goals']:.2f}",
        )
        self.assertIn("not your actual recorded income", response.data["reply"])

    @patch("apps.assistant.views.call_llm")
    def test_literacy_question_returns_llm_answer(self, mock_llm):
        self.authenticate()
        literacy_reply = (
            "An emergency fund is money set aside for unexpected costs, "
            "kept separate from day-to-day business cash."
        )
        mock_llm.side_effect = [
            classify(INTENT_GENERAL_QUESTION, question_type="literacy"),
            literacy_reply,
        ]
        response = self.ask("what is an emergency fund")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["intent"], INTENT_GENERAL_QUESTION)
        self.assertEqual(response.data["reply"], literacy_reply)
        self.assertEqual(response.data["facts"]["question_type"], "literacy")
        self.assertEqual(mock_llm.call_count, 2)
        self.assertIn("emergency fund", mock_llm.call_args.args[1])

    @patch("apps.assistant.views.call_llm")
    def test_check_summary_without_transactions_uses_template(self, mock_llm):
        self.authenticate()
        mock_llm.return_value = classify(INTENT_CHECK_SUMMARY, period="weekly")
        response = self.ask("How did this week go?")
        self.assertEqual(response.data["intent"], INTENT_CHECK_SUMMARY)
        self.assertEqual(response.data["reply"], NO_TRANSACTIONS_REPLY)
        self.assertEqual(response.data["facts"], {})
        self.assertEqual(mock_llm.call_count, 1)

    @patch("apps.assistant.views.call_llm")
    def test_retirement_check_without_profile_uses_template(self, mock_llm):
        self.authenticate()
        mock_llm.return_value = classify(INTENT_RETIREMENT_CHECK)
        response = self.ask("Am I on track for retirement?")
        self.assertEqual(response.data["intent"], INTENT_RETIREMENT_CHECK)
        self.assertEqual(response.data["reply"], NO_RETIREMENT_REPLY)
        self.assertEqual(response.data["facts"], {})
        self.assertEqual(mock_llm.call_count, 1)

    @patch("apps.assistant.views.call_llm")
    def test_how_much_save_without_goal_or_amount_uses_template(self, mock_llm):
        self.authenticate()
        mock_llm.return_value = classify(INTENT_HOW_MUCH_SAVE)
        response = self.ask("How much is left on my goal?")
        self.assertEqual(response.data["intent"], INTENT_HOW_MUCH_SAVE)
        self.assertEqual(response.data["reply"], NO_GOAL_REPLY)
        self.assertEqual(mock_llm.call_count, 1)

    @patch("apps.assistant.views.call_llm")
    def test_personal_general_question_uses_logged_summary(self, mock_llm):
        self.authenticate()
        self.seed_money()
        mock_llm.side_effect = [
            classify(INTENT_GENERAL_QUESTION, question_type="personal"),
            "You have income, expenses, and an estimated profit for this week.",
        ]
        response = self.ask("How am I doing with my money?")
        self.assertEqual(response.data["intent"], INTENT_GENERAL_QUESTION)
        self.assertEqual(response.data["facts"]["total_income"], "100000.00")
        self.assertEqual(response.data["facts"]["total_expenses"], "20000.00")
        self.assertIn("income", response.data["reply"])
        self.assertEqual(mock_llm.call_count, 2)

    @patch("apps.assistant.views.call_llm")
    def test_low_confidence_falls_back_without_second_llm_or_writes(self, mock_llm):
        self.authenticate()
        mock_llm.return_value = classify(INTENT_RECORD_TRANSACTION, confidence=0.2, amount="99")
        response = self.ask("asdfgh")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["intent"], INTENT_GENERAL_QUESTION)
        self.assertEqual(response.data["reply"], LOW_CONFIDENCE_REPLY)
        self.assertEqual(response.data["facts"], {})
        self.assertEqual(mock_llm.call_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)

    @patch("apps.assistant.views.call_llm")
    def test_invalid_classification_json_falls_back(self, mock_llm):
        self.authenticate()
        mock_llm.return_value = "I think this is about money"
        response = self.ask("maybe")
        self.assertEqual(response.data["intent"], INTENT_GENERAL_QUESTION)
        self.assertEqual(response.data["reply"], LOW_CONFIDENCE_REPLY)
        self.assertEqual(mock_llm.call_count, 1)

    def test_empty_question_is_rejected(self):
        self.authenticate()
        response = self.ask("   ")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("message", response.data)

    @override_settings(GEMINI_API_KEY="")
    @patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False)
    @patch("apps.assistant.llm.load_dotenv")
    def test_missing_gemini_key_returns_friendly_error(self, mock_dotenv):
        self.authenticate()
        response = self.ask("Can I afford 10000?")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("Gemini", response.data["detail"])
        self.assertNotIn("GEMINI_API_KEY=", str(response.data))
        self.assertNotIn("AQ.", str(response.data))

    @patch("apps.assistant.views.call_llm", side_effect=LLMError("I could not reach the assistant right now. Please try again."))
    def test_gemini_failure_returns_friendly_error(self, mock_llm):
        self.authenticate()
        response = self.ask("Can I afford 10000?")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data["detail"],
            "I could not reach the assistant right now. Please try again.",
        )
        self.assertNotIn("traceback", str(response.data).lower())


class GeminiClientTests(SimpleTestCase):
    @override_settings(GEMINI_API_KEY="", GEMINI_MODEL="gemini-3.6-flash")
    @patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False)
    @patch("apps.assistant.llm.load_dotenv")
    def test_call_llm_requires_gemini_key(self, mock_dotenv):
        with self.assertRaises(LLMError) as ctx:
            call_llm("system", "hello")
        self.assertIn("Gemini", str(ctx.exception))

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-3.6-flash")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-3.6-flash"}, clear=False)
    @patch("apps.assistant.llm.load_dotenv")
    @patch("apps.assistant.llm.genai.Client")
    def test_call_llm_returns_gemini_text(self, mock_client_cls, mock_dotenv):
        mock_chat = mock_client_cls.return_value.chats.create.return_value
        mock_chat.send_message.return_value = SimpleNamespace(text="  You can afford this.  ", candidates=[])
        text = call_llm("system", "Can I afford 10000?")
        self.assertEqual(text, "You can afford this.")
        mock_client_cls.assert_called_once_with(api_key="test-key")
        mock_client_cls.return_value.chats.create.assert_called_once()
        self.assertEqual(
            mock_client_cls.return_value.chats.create.call_args.kwargs["model"],
            "gemini-3.6-flash",
        )
        mock_chat.send_message.assert_called_once_with("Can I afford 10000?")

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-3.6-flash")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-3.6-flash"}, clear=False)
    @patch("apps.assistant.llm.load_dotenv")
    @patch("apps.assistant.llm.genai.Client")
    def test_call_llm_maps_api_failure(self, mock_client_cls, mock_dotenv):
        mock_client_cls.return_value.chats.create.side_effect = RuntimeError("network")
        with self.assertRaises(LLMError) as ctx:
            call_llm("system", "hello")
        self.assertEqual(str(ctx.exception), "I could not reach the assistant right now. Please try again.")

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-3.6-flash")
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-3.6-flash"}, clear=False)
    @patch("apps.assistant.llm.load_dotenv")
    @patch("apps.assistant.llm.genai.Client")
    def test_call_llm_rejects_empty_gemini_text(self, mock_client_cls, mock_dotenv):
        mock_chat = mock_client_cls.return_value.chats.create.return_value
        mock_chat.send_message.return_value = SimpleNamespace(text="  ", candidates=[])
        with self.assertRaises(LLMError) as ctx:
            call_llm("system", "hello")
        self.assertIn("unexpected", str(ctx.exception).lower())


class DashboardTranslationTests(SimpleTestCase):
    def test_luganda_covers_modal_and_category_keys(self):
        from apps.assistant.translations import DASHBOARD_LABELS, ENGLISH_LABELS

        luganda = DASHBOARD_LABELS["luganda"]
        for key in ENGLISH_LABELS:
            self.assertIn(key, luganda)
            self.assertTrue(str(luganda[key]).strip(), key)
        self.assertNotEqual(luganda["update_retirement"], ENGLISH_LABELS["update_retirement"])
        self.assertNotEqual(luganda["income"], ENGLISH_LABELS["income"])
        self.assertNotEqual(luganda["expense"], ENGLISH_LABELS["expense"])
        self.assertNotEqual(luganda["cat_sales"], ENGLISH_LABELS["cat_sales"])
        self.assertNotEqual(luganda["cat_rent"], ENGLISH_LABELS["cat_rent"])
        self.assertNotEqual(luganda["current_age"], ENGLISH_LABELS["current_age"])
        self.assertNotEqual(luganda["savings_goals"], ENGLISH_LABELS["savings_goals"])
        self.assertNotEqual(luganda["goal_type_emergency_fund"], ENGLISH_LABELS["goal_type_emergency_fund"])
        self.assertNotEqual(luganda["save_goal"], ENGLISH_LABELS["save_goal"])
        self.assertNotEqual(luganda["nav_assistant"], ENGLISH_LABELS["nav_assistant"])
        self.assertNotEqual(luganda["your_profile"], ENGLISH_LABELS["your_profile"])
        self.assertNotEqual(luganda["partner_accounts"], ENGLISH_LABELS["partner_accounts"])
        for language in SUPPORTED_LANGUAGES:
            pack = DASHBOARD_LABELS[language]
            self.assertTrue(pack["nav_dashboard"])
            self.assertTrue(pack["page_title_assistant"])


class HomePageI18nTests(APITestCase):
    def test_home_embeds_language_switcher_and_luganda_labels(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="dash-language"', html)
        self.assertIn('data-i18n="current_age"', html)
        self.assertIn("Tereeza pulani y'okuwummula", html)
        self.assertIn("Obutunda", html)
        self.assertIn("Ennyingiza", html)
        self.assertIn("Pesa y'ennyumba", html)

    def test_goals_page_embeds_luganda_labels(self):
        response = self.client.get("/goals/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-i18n="savings_goals"', html)
        self.assertIn('data-i18n="add_a_goal"', html)
        self.assertIn("Ebiruubirirwa by'okutereka", html)
        self.assertIn("Ensawo y'akatyabaga", html)
        self.assertIn("Tereka goolo", html)

    def test_removed_commitments_page_is_not_exposed(self):
        self.assertEqual(self.client.get("/commitments/").status_code, 404)

