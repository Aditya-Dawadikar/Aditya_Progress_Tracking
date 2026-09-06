from django.contrib import admin

from .models import Category, Goal, GoalBoard, Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_at"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "color", "created_by", "created_at"]


@admin.register(GoalBoard)
class GoalBoardAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    list_filter = ["created_by"]


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ["title", "board", "parent", "owner", "category", "status", "start_date", "end_date", "progress_percent"]
    list_filter = ["status", "board", "category"]
    search_fields = ["title", "description"]
    autocomplete_fields = ["parent"]
