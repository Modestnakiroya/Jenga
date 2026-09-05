from django.contrib import admin

from apps.retirement.models import RetirementProfile


@admin.register(RetirementProfile)
class RetirementProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "current_age",
        "desired_retirement_age",
        "desired_retirement_fund",
        "current_monthly_contribution",
    )
    search_fields = ("user__phone_number",)
