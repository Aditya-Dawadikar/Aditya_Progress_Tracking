from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.boards_list, name="boards_list"),

    path("whoami/", views.whoami, name="whoami"),
    path("whoami/logout/", views.whoami_logout, name="whoami_logout"),

    path("boards/new/", views.board_create, name="board_create"),
    path("boards/<int:pk>/", views.board_detail, name="board_detail"),
    path("boards/<int:pk>/edit/", views.board_edit, name="board_edit"),
    path("boards/<int:pk>/delete/", views.board_delete, name="board_delete"),

    path("goals/new/", views.goal_create, name="goal_create"),
    path("goals/<int:pk>/", views.goal_detail, name="goal_detail"),
    path("goals/<int:pk>/edit/", views.goal_edit, name="goal_edit"),
    path("goals/<int:pk>/delete/", views.goal_delete, name="goal_delete"),

    path("reorder/", views.goal_reorder, name="goal_reorder"),

    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("members/<slug:slug>/", views.member_profile, name="member_profile"),
]
