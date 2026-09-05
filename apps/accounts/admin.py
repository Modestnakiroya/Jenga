from django.contrib import admin

from apps.accounts.models import BusinessProfile, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "full_name", "is_staff", "is_active")
    search_fields = ("phone_number", "full_name", "email")
    ordering = ("phone_number",)
    readonly_fields = ("last_login", "date_joined")


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ("business_name", "user", "business_type", "tracking_frequency")
    search_fields = ("business_name", "user__phone_number")
    list_filter = ("business_type", "tracking_frequency")
