from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings, RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User, BusinessProfile, PartnerAccount
from apps.goals.models import Goal
from apps.assistant.llm import LLMError
from .admin import SaccoAccessAdmin
from .models import Sacco, SaccoAccess, SaccoMembership, SavingsSnapshot
from .services import personal_insights, sacco_report


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InsightsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("+256700123450", "TestPass123!", full_name="Private Name")
        BusinessProfile.objects.create(user=self.user, business_name="Private Business", business_type="shop_owner")
        self.client.force_authenticate(self.user)

    def account(self, **kwargs):
        values = dict(user=self.user, institution_name="Sample Bank", institution_type="bank", account_name="Savings",
                      interest_rate="12", minimum_deposit="100", terms_verified=True, terms_updated_on=timezone.localdate())
        values.update(kwargs)
        return PartnerAccount.objects.create(**values)

    def test_one_month_projection_and_goal_facts(self):
        account = self.account()
        Goal.objects.create(user=self.user, name="Stock", goal_type="business_growth", target_amount=1000, current_saved_amount=400)
        result = self.client.post(reverse("personal-insights"), {"amount":"1000"}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["accounts"][0]["estimated_interest"], "10.00")
        self.assertEqual(result.data["accounts"][0]["estimated_balance"], "1010.00")
        self.assertEqual(result.data["recommended_account_id"], account.pk)
        self.assertEqual(result.data["saved_in_goals"], "400.00")
        self.assertEqual(result.data["goals"][0]["remaining"], "600.00")

    def test_monthly_rate_zero_rate_missing_terms_and_currency(self):
        self.account(interest_rate="2", interest_period="monthly")
        self.account(interest_rate="0", account_name="Zero")
        self.account(interest_rate=None, account_name="Unknown")
        self.account(currency="USD")
        facts = personal_insights(self.user, Decimal("1000"), "UGX", 1)
        self.assertEqual(len(facts["accounts"]), 3)
        by_name = {a["account"]: a for a in facts["accounts"]}
        self.assertEqual(by_name["Savings"]["estimated_interest"], "20.00")
        self.assertEqual(by_name["Zero"]["estimated_interest"], "0.00")
        self.assertIsNone(by_name["Unknown"]["estimated_balance"])

    def test_unverified_stale_and_unaffordable_accounts_not_recommended(self):
        self.account(terms_verified=False)
        self.account(minimum_deposit="2000")
        self.account(terms_updated_on=timezone.localdate()-timedelta(days=91))
        self.account(minimum_deposit=None)
        result = personal_insights(self.user, Decimal("1000"), "UGX", 1)
        self.assertIsNone(result["recommended_account_id"])

    def test_personal_endpoint_validation_and_authentication(self):
        for payload in ({"amount":0}, {"amount":100,"months":0}, {"amount":100,"months":13}, {"amount":100,"currency":"EUR"}):
            self.assertEqual(self.client.post(reverse("personal-insights"),payload,format="json").status_code,400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(reverse("personal-insights"),{"amount":100},format="json").status_code,401)

    @patch("apps.insights.views.call_llm", side_effect=LLMError("unavailable"))
    def test_ai_failure_preserves_calculations_without_sending_private_data(self, llm):
        self.account()
        response = self.client.post(reverse("personal-insights"), {"amount":1000,"ai_summary":True}, format="json")
        self.assertEqual(response.status_code,200)
        self.assertIn("ai_status",response.data)
        prompt = str(llm.call_args)
        for secret in ("Private Name", "Private Business", "Sample Bank", self.user.phone_number, "1000"):
            self.assertNotIn(secret,prompt)

    def test_user_cannot_grant_role_or_verify_terms(self):
        response=self.client.patch(reverse("profile"),{"role":"sacco","is_superuser":True,"is_staff":True},format="json")
        self.assertEqual(response.status_code,200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_staff)
        self.assertEqual(response.data["role"],"user")
        response=self.client.post(reverse("partner-accounts"),{"institution_name":"Test","institution_type":"bank","account_name":"Savings","terms_verified":True},format="json")
        self.assertEqual(response.status_code,201)
        self.assertFalse(response.data["terms_verified"])

    def test_grant_revocation_and_admin_only_management(self):
        from django.contrib.admin.sites import AdminSite
        sacco=Sacco.objects.create(name="Approved SACCO")
        self.assertEqual(self.client.get(reverse("sacco-insights")).status_code,403)
        grant=SaccoAccess.objects.create(user=self.user,sacco=sacco)
        self.assertEqual(self.client.get(reverse("profile")).data["role"],"sacco")
        self.assertEqual(self.client.get(reverse("sacco-insights")).status_code,200)
        grant.is_active=False;grant.save()
        self.assertEqual(self.client.get(reverse("sacco-insights")).status_code,403)
        request=RequestFactory().get("/");request.user=self.user
        model_admin=SaccoAccessAdmin(SaccoAccess,AdminSite())
        self.assertFalse(model_admin.has_add_permission(request))
        self.user.is_superuser=True
        self.assertTrue(model_admin.has_add_permission(request))

    def test_consent_tracks_and_withdrawal_deletes_history(self):
        goal=Goal.objects.create(user=self.user,name="Stock",goal_type="business_growth",target_amount=1000,current_saved_amount=100)
        self.assertFalse(SavingsSnapshot.objects.filter(user=self.user).exists())
        self.client.patch(reverse("profile"),{"share_sacco_insights":True},format="json")
        self.assertEqual(SavingsSnapshot.objects.get(user=self.user).amount,100)
        goal.current_saved_amount=200;goal.save()
        self.assertEqual(SavingsSnapshot.objects.get(user=self.user).amount,200)
        self.client.patch(reverse("profile"),{"share_sacco_insights":False},format="json")
        self.assertFalse(SavingsSnapshot.objects.filter(user=self.user).exists())

    def test_historical_report_threshold_scope_and_no_personal_fields(self):
        sacco=Sacco.objects.create(name="Group")
        other=Sacco.objects.create(name="Other")
        end=timezone.localdate().replace(day=1)-timedelta(days=1)
        old=end.replace(day=1)-timedelta(days=1)
        for i in range(5):
            user=User.objects.create_user(f"+25671000000{i}","Pass123!",share_sacco_insights=True,full_name="Secret")
            BusinessProfile.objects.create(user=user,business_name="Secret",business_type="shop_owner")
            SaccoMembership.objects.create(user=user,sacco=sacco)
            SavingsSnapshot.objects.create(user=user,date=old,amount=100)
            SavingsSnapshot.objects.create(user=user,date=end,amount=120)
            if i==3:
                self.assertIsNone(sacco_report(sacco)["growth_percent"])
        result=sacco_report(sacco)
        self.assertEqual(result["growth_percent"],"20")
        self.assertEqual(result["sectors"],[{"sector":"Shop owner","share_of_visible_savings_percent":"100"}])
        self.assertIsNone(sacco_report(other)["growth_percent"])
        self.assertNotIn("Secret",str(result))
        self.assertNotIn("user_id",str(result))
        self.assertNotIn("amount",result)
        # Individual membership changes require fresh consent and erase old history.
        membership=SaccoMembership.objects.get(user=user)
        membership.sacco=other;membership.save()
        user.refresh_from_db()
        self.assertFalse(user.share_sacco_insights)
        self.assertFalse(SavingsSnapshot.objects.filter(user=user).exists())

    def test_role_does_not_allow_phone_only_password_reset(self):
        SaccoAccess.objects.create(user=self.user,sacco=Sacco.objects.create(name="Group"))
        self.client.force_authenticate(None)
        response=self.client.post("/api/v1/auth/reset-password/",{"phone_number":self.user.phone_number,"password":"Hijack123!"},format="json")
        self.assertEqual(response.status_code,404)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("TestPass123!"))


    def test_sacco_cannot_read_another_users_records(self):
        SaccoAccess.objects.create(user=self.user,sacco=Sacco.objects.create(name="Test"))
        other=User.objects.create_user("+256700777777","OtherPass123!",full_name="Other Person")
        Goal.objects.create(user=other,name="Secret Goal",goal_type="personal",target_amount=1000,current_saved_amount=700)
        PartnerAccount.objects.create(user=other,institution_name="Secret Bank",institution_type="bank",account_name="Secret Account")
        self.assertEqual(self.client.get("/api/v1/goals/").data,[])
        self.assertEqual(self.client.get(reverse("partner-accounts")).data,[])
        data=self.client.post(reverse("personal-insights"),{"amount":1000},format="json").data
        self.assertEqual(data["goals"],[])
        self.assertEqual(data["accounts"],[])

    def test_account_admin_form_hashes_password(self):
        from apps.accounts.forms import AccountCreationForm
        form=AccountCreationForm(data={"phone_number":"+256700999999","full_name":"Admin Created","password1":"StrongNewPassword123!","password2":"StrongNewPassword123!"})
        self.assertTrue(form.is_valid(),form.errors)
        user=form.save()
        self.assertTrue(user.check_password("StrongNewPassword123!"))


    def test_deleting_opted_in_user_does_not_recreate_history(self):
        self.user.share_sacco_insights=True;self.user.save()
        Goal.objects.create(user=self.user,name="Delete",goal_type="personal",target_amount=100,current_saved_amount=50)
        key=self.user.pk
        self.user.delete()
        self.assertFalse(SavingsSnapshot.objects.filter(user_id=key).exists())
