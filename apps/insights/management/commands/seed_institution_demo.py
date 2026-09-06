"""Create isolated fictional institutions; never attach fabricated history to real members."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, BusinessProfile
from apps.goals.models import Goal
from apps.insights.models import Bank, Sacco, BankAccess, SaccoAccess, BankMembership, SaccoMembership, SavingsSnapshot

DEMO_PASSWORD = "JengaDemo2026!"


class Command(BaseCommand):
    help = "Create a fictional SACCO and bank with member-sector savings history (local DEBUG only)."

    @transaction.atomic
    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if not settings.DEBUG or ("sqlite" not in database["ENGINE"] and database.get("HOST") not in ("localhost", "127.0.0.1", "::1")):
            raise CommandError("Demo data is restricted to a local development database with DEBUG=True.")
        today = timezone.localdate()
        for group, model, access, membership, field in [
            (1, Sacco, SaccoAccess, SaccoMembership, "sacco"),
            (2, Bank, BankAccess, BankMembership, "bank"),
        ]:
            # Reserved fictional UK mobile range: these accounts must never receive messages.
            representative_phone = f"+447700900{group}00"
            expected_name = f"DEMO {field.upper()} representative"
            existing = User.objects.filter(phone_number=representative_phone).first()
            if existing:
                if existing.full_name != expected_name or existing.email != f"representative{group}@jenga.example":
                    raise CommandError("Demo phone collision; no existing account was changed.")
                self.stdout.write(f"DEMO {field.upper()} already exists; skipped without changing its data.")
                continue
            name = f"DEMO Jenga {field.upper()} (fictional)"
            if model.objects.filter(name=name).exists():
                raise CommandError("Demo institution name is already in use; no data changed.")
            institution = model.objects.create(name=name)
            representative = User.objects.create_user(representative_phone, DEMO_PASSWORD,
                full_name=expected_name, email=f"representative{group}@jenga.example")
            BusinessProfile.objects.create(user=representative, business_name=name, business_type="other")
            access.objects.create(user=representative, **{field: institution})
            for index in range(18):
                phone = f"+447700900{group}{index + 1:02d}"
                if User.objects.filter(phone_number=phone).exists():
                    raise CommandError("Demo member phone collision; changes rolled back.")
                sector = ["market_vendor", "shop_owner", "tailor"][index // 6]
                # Members have no usable login password; only representatives need demo access.
                member = User(phone_number=phone, full_name=f"DEMO {field} member {index + 1:02d}",
                              email=f"member{group}-{index}@jenga.example", share_sacco_insights=True)
                member.set_unusable_password()
                member.save()
                membership.objects.create(user=member, **{field: institution})
                BusinessProfile.objects.create(user=member, business_name=f"DEMO {sector} {index + 1}", business_type=sector)
                baseline = Decimal(100000 + index * 15000)
                daily = Decimal((index // 6 + 1) * 1000 + group * 500)
                balance = baseline + 180 * daily
                Goal.objects.create(user=member, name="DEMO business savings", goal_type="business_growth",
                                    target_amount=balance * 2, current_saved_amount=balance, target_date=today + timedelta(days=180))
                # Deliberately simulated daily history, including a pre-range opening balance.
                # Goal signals already created today's snapshot; fill only earlier days.
                SavingsSnapshot.objects.bulk_create([
                    SavingsSnapshot(user=member, date=today-timedelta(days=180-day), amount=baseline+day*daily)
                    for day in range(180)
                ])
            self.stdout.write(self.style.SUCCESS(f"Created {name}: 18 members, 3 sectors, 181 days of savings history. Representative: {representative_phone}"))
        self.stdout.write("Demo-only login password is documented in docs/institution-demo.md. No messages were sent.")
