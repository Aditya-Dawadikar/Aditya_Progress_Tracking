from django.contrib import admin

from .models import (
    AttemptEvent,
    ExpectedFailureMode,
    GeneratedTestCase,
    Pattern,
    Problem,
    ProblemAttempt,
    SubmissionFailure,
    Test,
    TestPlan,
    TestPlanProblem,
)


@admin.register(Pattern)
class PatternAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    list_display = ["leetcode_number", "title", "difficulty", "primary_pattern"]
    list_filter = ["difficulty", "primary_pattern"]
    search_fields = ["title", "leetcode_number"]
    autocomplete_fields = ["primary_pattern", "secondary_patterns"]


class ExpectedFailureModeInline(admin.TabularInline):
    model = ExpectedFailureMode
    extra = 0


class TestPlanProblemInline(admin.TabularInline):
    model = TestPlanProblem
    extra = 0
    fields = ["order", "problem", "novelty", "expected_primary_pattern"]
    autocomplete_fields = ["problem", "expected_primary_pattern"]


@admin.register(TestPlan)
class TestPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "scheduled_date", "status", "problem_count", "schema_version"]
    list_filter = ["status"]
    inlines = [TestPlanProblemInline]


@admin.register(TestPlanProblem)
class TestPlanProblemAdmin(admin.ModelAdmin):
    list_display = ["test_plan", "problem", "order", "novelty", "expected_primary_pattern"]
    list_filter = ["novelty"]
    autocomplete_fields = ["problem", "expected_primary_pattern", "expected_secondary_patterns"]
    inlines = [ExpectedFailureModeInline]


class ProblemAttemptInline(admin.TabularInline):
    model = ProblemAttempt
    extra = 0
    fields = ["order", "problem", "status", "solved", "hints_used", "confidence"]


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ["name", "date", "status", "test_plan", "problem_count", "solved_count"]
    list_filter = ["status"]
    inlines = [ProblemAttemptInline]


class AttemptEventInline(admin.TabularInline):
    model = AttemptEvent
    extra = 0


class GeneratedTestCaseInline(admin.TabularInline):
    model = GeneratedTestCase
    extra = 0


class SubmissionFailureInline(admin.TabularInline):
    model = SubmissionFailure
    extra = 0


@admin.register(ProblemAttempt)
class ProblemAttemptAdmin(admin.ModelAdmin):
    list_display = ["test", "problem", "status", "solved", "pattern_identification_result"]
    list_filter = ["test", "status", "pattern_identification_result"]
    inlines = [AttemptEventInline, GeneratedTestCaseInline, SubmissionFailureInline]


admin.site.register(AttemptEvent)
admin.site.register(GeneratedTestCase)
admin.site.register(SubmissionFailure)
