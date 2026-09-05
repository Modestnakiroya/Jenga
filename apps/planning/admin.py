from django.contrib import admin

from apps.planning.models import UpcomingExpense


@admin.register(UpcomingExpense)
class UpcomingExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "user", "amount", "expected_date")
    list_filter = ("expected_date",)
    search_fields = ("description", "user__phone_number")
