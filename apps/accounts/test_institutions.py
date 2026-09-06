from datetime import timedelta
from decimal import Decimal
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.accounts.models import User, BusinessProfile
from apps.insights.models import Bank, BankAccess, BankMembership, Sacco, SavingsSnapshot
from apps.insights.services import sacco_report


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InstitutionTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('+256700111111','Admin123!',full_name='Admin')
        self.bank = Bank.objects.create(name='Test Bank')
        self.sacco = Sacco.objects.create(name='Test SACCO')

    def test_admin_logout_redirects_to_landing(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post('/admin/logout/'), '/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/admin/').status_code, 302)

    def test_bank_representative_creation_login_and_revocation(self):
        self.client.force_login(self.admin)
        response = self.client.post('/admin/', {'action':'add_user','role':'bank','bank':self.bank.pk,'phone_number':'0700222222','full_name':'Bank Representative','password1':'SecurePass123!','password2':'SecurePass123!'})
        self.assertEqual(response.status_code,302)
        self.client.logout()
        response = self.client.post('/api/v1/auth/sacco/login/', {'phone_number':'0700222222','password':'SecurePass123!'},format='json')
        self.assertEqual(response.status_code,200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+response.data['access'])
        self.assertEqual(self.client.get('/api/v1/profile/').data['role'],'bank')
        report=self.client.get('/api/v1/insights/sacco/')
        self.assertEqual(report.status_code,200)
        self.assertEqual(report.data['sacco'],self.bank.name)
        BankAccess.objects.update(is_active=False)
        self.assertEqual(self.client.get('/api/v1/insights/sacco/').status_code,403)

    def test_institution_directory_and_partner_selection(self):
        self.assertEqual(self.client.get('/api/v1/institutions/').status_code,401)
        self.client.force_authenticate(self.admin)
        directory=self.client.get('/api/v1/institutions/').data
        self.assertEqual({i['name'] for i in directory},{self.bank.name,self.sacco.name})
        payload={'institution':f'bank:{self.bank.pk}','institution_name':'Forged','institution_type':'sacco','account_name':'Savings','currency':'UGX'}
        response=self.client.post('/api/v1/partners/accounts/',payload,format='json')
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.data['institution_name'],self.bank.name)
        self.assertEqual(response.data['institution_type'],'bank')
        payload['institution']='bank:99999'
        self.assertEqual(self.client.post('/api/v1/partners/accounts/',payload,format='json').status_code,400)
        self.assertFalse(BankMembership.objects.filter(user=self.admin).exists())

    def test_bank_report_scopes_members_and_preserves_privacy(self):
        other=Bank.objects.create(name='Other bank')
        end=timezone.localdate().replace(day=1)-timedelta(days=1)
        previous=end.replace(day=1)-timedelta(days=1)
        for n in range(10):
            member=User.objects.create_user(f'+25670033{n:04d}','Member123!',full_name=f'Private {n}',share_sacco_insights=True)
            BusinessProfile.objects.create(user=member,business_name='Private business',business_type='trader')
            BankMembership.objects.create(user=member,bank=self.bank if n<5 else other)
            SavingsSnapshot.objects.create(user=member,date=previous,amount=100)
            SavingsSnapshot.objects.create(user=member,date=end,amount=120 if n<5 else 900)
        report=sacco_report(self.bank,bank=True)
        self.assertEqual(report['growth_percent'],'20')
        earlier = sacco_report(self.bank, bank=True, month=previous.strftime('%Y-%m'))
        self.assertIsNone(earlier['growth_percent'])
        self.assertEqual(earlier['period_end'], previous.isoformat())
        self.assertEqual(earlier['member_count'], report['member_count'])
        self.assertEqual(len(report['available_months']), 24)
        self.assertNotIn('Private',str(report))
        membership=BankMembership.objects.filter(bank=self.bank).first()
        membership.bank=other
        membership.save()
        membership.user.refresh_from_db()
        self.assertFalse(membership.user.share_sacco_insights)
        self.assertFalse(SavingsSnapshot.objects.filter(user=membership.user).exists())


    def test_membership_counts_are_scoped_and_available_without_financial_history(self):
        from apps.insights.models import SaccoMembership
        other_bank = Bank.objects.create(name="Unrelated bank")
        for index, active in enumerate([True, True, False]):
            user = User.objects.create_user(f"+25670088{index:04d}", "Member123!", is_active=active)
            BankMembership.objects.create(user=user, bank=self.bank)
        outsider = User.objects.create_user("+256700999999", "Member123!")
        BankMembership.objects.create(user=outsider, bank=other_bank)
        SaccoMembership.objects.create(user=outsider, sacco=self.sacco)
        report = sacco_report(self.bank, bank=True)
        self.assertEqual(report["member_count"], 2)
        self.assertIsNone(report["growth_percent"])
        self.assertEqual(report["sectors"], [])
        self.assertEqual(sacco_report(self.sacco)["member_count"], 1)
        self.assertEqual(sacco_report(Bank.objects.create(name="Empty bank"), bank=True)["member_count"], 0)
        self.assertNotIn(outsider.phone_number, str(report))
        BankMembership.objects.filter(bank=self.bank, user__is_active=True).first().delete()
        self.assertEqual(sacco_report(self.bank, bank=True)["member_count"], 1)


    def test_reporting_month_validation_and_access(self):
        from apps.insights.services import reporting_months
        representative = User.objects.create_user("+256700777123", "Secure123!")
        BankAccess.objects.create(user=representative, bank=self.bank)
        self.client.force_authenticate(representative)
        for month in ["2026-99", "bad", "2999-01", ""]:
            self.assertEqual(self.client.get('/api/v1/insights/sacco/', {'month':month}).status_code, 400)
        chosen = reporting_months()[2]['value']
        response = self.client.get('/api/v1/insights/sacco/', {'month':chosen})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['selected_month'], chosen)
        BankAccess.objects.update(is_active=False)
        self.assertEqual(self.client.get('/api/v1/insights/sacco/', {'month':chosen}).status_code, 403)


    def test_two_day_current_range_and_validation(self):
        today = timezone.localdate()
        start = today - timedelta(days=1)
        representative = User.objects.create_user("+256700777124", "Secure123!")
        BankAccess.objects.create(user=representative, bank=self.bank)
        self.client.force_authenticate(representative)
        for n in range(5):
            member = User.objects.create_user(f"+25670044{n:04d}", "Member123!", share_sacco_insights=True)
            BankMembership.objects.create(user=member, bank=self.bank)
            SavingsSnapshot.objects.filter(user=member).delete()
            SavingsSnapshot.objects.create(user=member,date=start-timedelta(days=1),amount=100)
            SavingsSnapshot.objects.create(user=member,date=today,amount=125)
        response = self.client.get('/api/v1/insights/sacco/', {'start_date':start.isoformat(), 'end_date':today.isoformat()})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['growth_percent'],'25')
        self.assertEqual(response.data['start_date'],start.isoformat())
        self.assertEqual(response.data['end_date'],today.isoformat())
        for query in [
            {'start_date':today.isoformat()},
            {'start_date':today.isoformat(),'end_date':start.isoformat()},
            {'start_date':start.isoformat(),'end_date':(today+timedelta(days=1)).isoformat()},
            {'start_date':'invalid','end_date':today.isoformat()},
        ]:
            self.assertEqual(self.client.get('/api/v1/insights/sacco/',query).status_code,400)
