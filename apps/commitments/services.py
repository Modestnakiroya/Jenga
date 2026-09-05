from django.utils import timezone

from apps.commitments.models import Commitment, CommitmentStatus


def get_due_commitments(user, reference_date=None):
    """Return overdue commitments that are still pending.

    A commitment is due when status is Pending and period_end is in the past.
    """
    today = reference_date or timezone.localdate()
    return Commitment.objects.filter(
        user=user,
        status=CommitmentStatus.PENDING,
        period_end__lt=today,
    )
