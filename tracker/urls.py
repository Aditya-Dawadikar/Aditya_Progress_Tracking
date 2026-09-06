from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.boards_list, name="boards_list"),

    path("whoami/", views.whoami, name="whoami"),
    path("whoami/logout/", views.whoami_logout, name="whoami_logout"),

    path("boards/new/", views.board_create, name="board_create"),
    path("boards/<str:pk>/", views.board_detail, name="board_detail"),
    path("boards/<str:pk>/settings/", views.board_settings, name="board_settings"),
    path("boards/<str:pk>/edit/", views.board_edit, name="board_edit"),
    path("boards/<str:pk>/delete/", views.board_delete, name="board_delete"),
    path("boards/<str:pk>/export.json", views.board_export_json, name="board_export_json"),
    path("boards/<str:pk>/import/", views.board_import_json, name="board_import_json"),
    path("boards/<str:pk>/categories/", views.category_list, name="category_list"),

    path("goals/new/", views.goal_create, name="goal_create"),
    path("goals/<str:pk>/", views.goal_detail, name="goal_detail"),
    path("goals/<str:pk>/edit/", views.goal_edit, name="goal_edit"),
    path("goals/<str:pk>/delete/", views.goal_delete, name="goal_delete"),
    path("goals/<str:pk>/comments/", views.goal_comment_create, name="goal_comment_create"),
    path("goals/<str:pk>/tasks/", views.task_create, name="task_create"),
    path("tasks/<str:pk>/toggle/", views.task_toggle, name="task_toggle"),
    path("tasks/<str:pk>/delete/", views.task_delete, name="task_delete"),
    path("tasks/<str:pk>/comments/", views.task_comment_create, name="task_comment_create"),

    path("reorder/", views.goal_reorder, name="goal_reorder"),

    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("members/<slug:slug>/", views.member_profile, name="member_profile"),
]
