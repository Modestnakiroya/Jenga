from django.contrib import admin

from apps.transactions.models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "amount", "category", "date")
    list_filter = ("type", "category", "date")
    search_fields = ("description", "user__phone_number")
