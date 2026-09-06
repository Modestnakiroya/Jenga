from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import BusinessProfile, User, PartnerAccount
from apps.accounts.forms import AccountCreationForm, AccountChangeForm

admin.site.site_header = "Jenga administration"
admin.site.site_title = "Jenga admin"
admin.site.index_title = "Manage users, SACCOs and member access"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = AccountChangeForm
    add_form = AccountCreationForm
    fieldsets = (
        (None, {"fields": ("phone_number", "password")}),
        ("Profile", {"fields": ("full_name", "email", "preferred_language", "share_sacco_insights")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"fields": ("phone_number", "full_name", "email", "password1", "password2")}),)
    list_display = ("phone_number", "full_name", "is_staff", "is_active")
    search_fields = ("phone_number", "full_name", "email")
    ordering = ("phone_number",)
    readonly_fields = ("last_login", "date_joined", "share_sacco_insights")

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ("business_name", "user", "business_type", "tracking_frequency")
    search_fields = ("business_name", "user__phone_number")
    list_filter = ("business_type", "tracking_frequency")



@admin.register(PartnerAccount)
class PartnerAccountAdmin(admin.ModelAdmin):
    list_display = ("institution_name", "account_name", "user", "interest_rate", "interest_period", "minimum_deposit", "currency")
    list_filter = ("institution_type", "currency")
    raw_id_fields = ("user",)

    def get_readonly_fields(self, request, obj=None):
        return () if request.user.is_superuser else ("terms_verified",)
