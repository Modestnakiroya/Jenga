from django.contrib import admin

from apps.goals.models import Goal


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "goal_type", "target_amount", "current_saved_amount", "status")
    list_filter = ("goal_type", "status")
    search_fields = ("name", "user__phone_number")
