from django.contrib import admin

from .models import Goal, GoalBoard, Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_at"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(GoalBoard)
class GoalBoardAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    list_filter = ["created_by"]


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ["title", "board", "parent", "owner", "status", "start_date", "end_date", "progress_percent"]
    list_filter = ["status", "board"]
    search_fields = ["title", "description", "category"]
    autocomplete_fields = ["parent"]
