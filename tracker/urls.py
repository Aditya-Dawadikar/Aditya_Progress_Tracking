from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("problems/", views.problem_list, name="problem_list"),
    path("problems/new/", views.problem_create, name="problem_create"),
    path("problems/<int:pk>/edit/", views.problem_edit, name="problem_edit"),

    path("test-plans/", views.test_plan_list, name="test_plan_list"),
    path("test-plans/import/", views.test_plan_import, name="test_plan_import"),
    path("test-plans/<int:pk>/", views.test_plan_detail, name="test_plan_detail"),
    path("test-plans/<int:pk>/mark-ready/", views.test_plan_mark_ready, name="test_plan_mark_ready"),
    path("test-plans/<int:pk>/start/", views.test_plan_start, name="test_plan_start"),
    path("test-plans/<int:pk>/skip/", views.test_plan_skip, name="test_plan_skip"),
    path("test-plans/<int:pk>/discard/", views.test_plan_discard, name="test_plan_discard"),

    path("tests/", views.test_list, name="test_list"),
    path("tests/new/", views.test_create, name="test_create"),
    path("tests/<int:pk>/", views.test_detail, name="test_detail"),
    path("tests/<int:pk>/add-problems/", views.test_add_problems, name="test_add_problems"),
    path("tests/<int:pk>/complete/", views.test_complete, name="test_complete"),
    path("tests/<int:pk>/export.csv", views.export_test_attempts_csv, name="export_test_attempts_csv"),

    path("tests/<int:test_pk>/attempts/<int:pk>/", views.attempt_detail, name="attempt_detail"),
    path("attempts/<int:pk>/start/", views.attempt_start, name="attempt_start"),
    path("attempts/<int:pk>/understood/", views.attempt_understood, name="attempt_understood"),
    path("attempts/<int:pk>/pattern-identified/", views.attempt_pattern_identified, name="attempt_pattern_identified"),
    path("attempts/<int:pk>/start-pseudocode/", views.attempt_start_pseudocode, name="attempt_start_pseudocode"),
    path("attempts/<int:pk>/start-test-design/", views.attempt_start_test_design, name="attempt_start_test_design"),
    path("attempts/<int:pk>/start-implementation/", views.attempt_start_implementation, name="attempt_start_implementation"),
    path("attempts/<int:pk>/submit/", views.attempt_submit, name="attempt_submit"),
    path("attempts/<int:pk>/failure-analysis/", views.attempt_add_failure_analysis, name="attempt_add_failure_analysis"),
    path("attempts/<int:pk>/abandon/", views.attempt_abandon, name="attempt_abandon"),
    path("attempts/<int:pk>/pause/", views.attempt_pause, name="attempt_pause"),
    path("attempts/<int:pk>/resume/", views.attempt_resume, name="attempt_resume"),
    path("attempts/<int:pk>/hint/", views.attempt_hint, name="attempt_hint"),
    path("attempts/<int:pk>/pattern-review/", views.attempt_pattern_review, name="attempt_pattern_review"),
    path("attempts/<int:pk>/test-cases/add/", views.attempt_add_test_case, name="attempt_add_test_case"),
    path("attempts/<int:pk>/test-cases/<int:tc_pk>/delete/", views.test_case_delete, name="test_case_delete"),
    path("attempts/<int:pk>/failures/<int:f_pk>/delete/", views.failure_delete, name="failure_delete"),

    path("export/tests.csv", views.export_tests_csv, name="export_tests_csv"),
    path("export/problems.csv", views.export_problems_csv, name="export_problems_csv"),
    path("export/attempts.csv", views.export_attempts_csv, name="export_attempts_csv"),
    path("export/events.csv", views.export_events_csv, name="export_events_csv"),
    path("export/test-cases.csv", views.export_test_cases_csv, name="export_test_cases_csv"),
    path("export/failures.csv", views.export_failures_csv, name="export_failures_csv"),
]
