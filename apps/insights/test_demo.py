from datetime import timedelta
from io import StringIO
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.accounts.models import User
from .models import Bank, Sacco, SavingsSnapshot
from .services import sacco_report


@override_settings(DEBUG=True, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InstitutionDemoTests(TestCase):
    def test_demo_reports_and_repeat_run(self):
        call_command("seed_institution_demo", stdout=StringIO())
        today = timezone.localdate()
        for institution, bank in [(Bank.objects.get(), True), (Sacco.objects.get(), False)]:
            report = sacco_report(institution, bank=bank, start_date=today-timedelta(days=1), end_date=today)
            self.assertEqual(report["member_count"], 18)
            self.assertEqual(len(report["sectors"]), 3)
            self.assertIsNotNone(report["growth_percent"])
        counts = (User.objects.count(), SavingsSnapshot.objects.count())
        call_command("seed_institution_demo", stdout=StringIO())
        self.assertEqual(counts, (User.objects.count(), SavingsSnapshot.objects.count()))

    @override_settings(DEBUG=False)
    def test_production_disabled(self):
        with self.assertRaises(CommandError):
            call_command("seed_institution_demo", stdout=StringIO())
        self.assertFalse(User.objects.exists())
