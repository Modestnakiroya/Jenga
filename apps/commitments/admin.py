from django.contrib import admin

from apps.commitments.models import Commitment


@admin.register(Commitment)
class CommitmentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "target_amount",
        "saved_amount",
        "period_end",
        "status",
    )
    list_filter = ("status",)
    search_fields = ("user__phone_number", "adjustment_reason")
