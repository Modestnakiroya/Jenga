from django.contrib import admin
from .models import Sacco, SaccoAccess, SaccoMembership


class SuperuserOnlyAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission


@admin.register(Sacco)
class SaccoAdmin(SuperuserOnlyAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(SaccoAccess)
class SaccoAccessAdmin(SuperuserOnlyAdmin):
    list_display = ("user", "sacco", "is_active")
    raw_id_fields = ("user",)
    list_filter = ("is_active", "sacco")
    search_fields = ("user__phone_number", "user__full_name", "sacco__name")
    autocomplete_fields = ("sacco",)


@admin.register(SaccoMembership)
class SaccoMembershipAdmin(SuperuserOnlyAdmin):
    list_display = ("user", "sacco")
    raw_id_fields = ("user",)
    list_filter = ("sacco",)
    search_fields = ("user__phone_number", "user__full_name", "sacco__name")
    autocomplete_fields = ("sacco",)
