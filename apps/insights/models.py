from django.conf import settings
from django.db import models


class Sacco(models.Model):
    name = models.CharField(max_length=180)

    def __str__(self):
        return self.name


class Bank(models.Model):
    name = models.CharField(max_length=180, unique=True)

    def __str__(self):
        return self.name


class SaccoAccess(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sacco_access")
    sacco = models.ForeignKey(Sacco, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"SACCO access: {self.sacco}"


class SaccoMembership(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sacco_membership")
    sacco = models.ForeignKey(Sacco, on_delete=models.CASCADE)


class SavingsSnapshot(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "date"], name="one_savings_snapshot_per_day")]
        ordering = ["date"]


class BankAccess(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_access")
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)


class BankMembership(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bank_membership")
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
