from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.commitments.services import get_due_commitments
from apps.sms_gateway.client import send_sms
from apps.sms_gateway.commands import format_amount, sms_label

REMINDER_COOLDOWN = timedelta(hours=24)


def send_due_commitment_reminders(reference_date=None, now=None):
    """SMS users who have a due pending commitment not reminded in the last 24 hours."""
    now = now or timezone.now()
    sent_count = 0
    for user in User.objects.all().iterator():
        language = (user.preferred_language or "english").lower()
        for commitment in get_due_commitments(user, reference_date=reference_date):
            if commitment.last_reminded_at and now - commitment.last_reminded_at < REMINDER_COOLDOWN:
                continue
            message = sms_label(
                language,
                "sms_commitment_reminder",
                amount=format_amount(commitment.target_amount),
            )
            if send_sms(user.phone_number, message) is None:
                continue
            commitment.last_reminded_at = now
            commitment.save(update_fields=["last_reminded_at"])
            sent_count += 1
    return sent_count


class Command(BaseCommand):
    help = "Send SMS reminders for due pending commitments not reminded in the last 24 hours."

    def handle(self, *args, **options):
        sent = send_due_commitment_reminders()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} commitment reminder(s)."))
