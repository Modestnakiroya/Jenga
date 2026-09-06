from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.accounts.models import User
from apps.goals.models import Goal
from .models import SavingsSnapshot, SaccoMembership, BankMembership


@transaction.atomic
def record_snapshot(user_id):
    if not User.objects.select_for_update().filter(pk=user_id, share_sacco_insights=True).first():
        return
    amount = Goal.objects.filter(user_id=user_id).exclude(status="abandoned").aggregate(total=Sum("current_saved_amount"))["total"] or Decimal("0")
    SavingsSnapshot.objects.update_or_create(user_id=user_id, date=timezone.localdate(), defaults={"amount": amount})


@receiver(post_save, sender=Goal)
@receiver(post_delete, sender=Goal)
def goal_changed(sender, instance, **kwargs):
    origin = kwargs.get("origin")
    if isinstance(origin, User) or getattr(origin, "model", None) is User:
        return
    record_snapshot(instance.user_id)


@receiver(post_save, sender=User)
def consent_changed(sender, instance, **kwargs):
    if instance.share_sacco_insights:
        record_snapshot(instance.pk)
    else:
        SavingsSnapshot.objects.filter(user=instance).delete()


@receiver(pre_save, sender=BankMembership)
@receiver(pre_save, sender=SaccoMembership)
def membership_changed(sender, instance, **kwargs):
    previous = sender.objects.filter(pk=instance.pk).first() if instance.pk else None
    if previous and (getattr(previous, "sacco_id", None) != getattr(instance, "sacco_id", None) or getattr(previous, "bank_id", None) != getattr(instance, "bank_id", None) or previous.user_id != instance.user_id):
        User.objects.filter(pk__in=[previous.user_id, instance.user_id]).update(share_sacco_insights=False)
        SavingsSnapshot.objects.filter(user_id__in=[previous.user_id, instance.user_id]).delete()


@receiver(post_delete, sender=BankMembership)
@receiver(post_delete, sender=SaccoMembership)
def membership_removed(sender, instance, **kwargs):
    User.objects.filter(pk=instance.user_id).update(share_sacco_insights=False)
    SavingsSnapshot.objects.filter(user_id=instance.user_id).delete()
