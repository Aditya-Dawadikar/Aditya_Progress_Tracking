import csv

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    AbandonForm,
    FailureAnalysisForm,
    PatternIdentifiedForm,
    PatternReviewForm,
    ProblemForm,
    SubmitForm,
    TestCaseForm,
    TestForm,
    TestPlanImportForm,
)
from .models import (
    AttemptEvent,
    GeneratedTestCase,
    Pattern,
    Problem,
    ProblemAttempt,
    SubmissionFailure,
    Test,
    TestPlan,
    TestPlanProblem,
)
from .services import analytics, testplan_import


def dashboard(request):
    recent_tests = Test.objects.all()[:10]
    latest_test = recent_tests.first()
    recent_plans = TestPlan.objects.all()[:5]
    return render(request, "tracker/dashboard.html", {
        "latest_test": latest_test,
        "recent_tests": recent_tests,
        "recent_plans": recent_plans,
    })


# ---------------------------------------------------------------------------
# Problem catalog
# ---------------------------------------------------------------------------

def problem_list(request):
    problems = Problem.objects.select_related("primary_pattern").all()

    query = request.GET.get("q", "").strip()
    if query:
        problems = problems.filter(Q(title__icontains=query) | Q(leetcode_number__icontains=query))

    difficulty = request.GET.get("difficulty", "")
    if difficulty:
        problems = problems.filter(difficulty=difficulty)

    pattern_id = request.GET.get("pattern", "")
    if pattern_id:
        problems = problems.filter(
            Q(primary_pattern_id=pattern_id) | Q(secondary_patterns__id=pattern_id)
        ).distinct()

    return render(request, "tracker/problem_list.html", {
        "problems": problems,
        "patterns": Pattern.objects.all(),
        "query": query,
        "difficulty": difficulty,
        "pattern_id": pattern_id,
        "difficulty_choices": Problem.DIFFICULTY_CHOICES,
    })


def problem_create(request):
    if request.method == "POST":
        form = ProblemForm(request.POST)
        if form.is_valid():
            problem = form.save()
            messages.success(request, f"Added problem: {problem}")
            return redirect("tracker:problem_list")
    else:
        form = ProblemForm()
    return render(request, "tracker/problem_form.html", {"form": form, "is_new": True})


def problem_edit(request, pk):
    problem = get_object_or_404(Problem, pk=pk)
    if request.method == "POST":
        form = ProblemForm(request.POST, instance=problem)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated problem: {problem}")
            return redirect("tracker:problem_list")
    else:
        form = ProblemForm(instance=problem)
    return render(request, "tracker/problem_form.html", {"form": form, "is_new": False, "problem": problem})


# ---------------------------------------------------------------------------
# Test Plans
# ---------------------------------------------------------------------------

def test_plan_list(request):
    plans = TestPlan.objects.all()
    return render(request, "tracker/test_plan_list.html", {"plans": plans})


def test_plan_import(request):
    if request.method == "POST":
        form = TestPlanImportForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data["json_file"]
            errors, warnings, _counts = testplan_import.validate(data)
            if errors:
                return render(request, "tracker/test_plan_import.html", {
                    "form": form, "errors": errors, "warnings": warnings,
                })
            plan = testplan_import.import_plan(data)
            for w in warnings:
                messages.warning(request, w)
            messages.success(request, f"Imported '{plan.name}' as a draft — review it below.")
            return redirect("tracker:test_plan_detail", pk=plan.pk)
    else:
        form = TestPlanImportForm()
    return render(request, "tracker/test_plan_import.html", {"form": form})


def test_plan_detail(request, pk):
    plan = get_object_or_404(TestPlan, pk=pk)
    plan_problems = plan.plan_problems.select_related(
        "problem", "expected_primary_pattern"
    ).prefetch_related("expected_secondary_patterns", "expected_failure_modes")
    return render(request, "tracker/test_plan_detail.html", {
        "plan": plan,
        "plan_problems": plan_problems,
    })


def test_plan_mark_ready(request, pk):
    plan = get_object_or_404(TestPlan, pk=pk)
    if request.method == "POST" and plan.status == TestPlan.STATUS_DRAFT:
        plan.status = TestPlan.STATUS_READY
        plan.save(update_fields=["status"])
    return redirect("tracker:test_plan_detail", pk=plan.pk)


def test_plan_start(request, pk):
    plan = get_object_or_404(TestPlan, pk=pk)
    if request.method != "POST" or plan.status not in (TestPlan.STATUS_DRAFT, TestPlan.STATUS_READY):
        return redirect("tracker:test_plan_detail", pk=plan.pk)

    test = Test.objects.create(
        test_plan=plan,
        name=plan.name,
        date=plan.scheduled_date or timezone.localdate(),
    )
    for pp in plan.plan_problems.all():
        ProblemAttempt.objects.create(
            test=test, problem=pp.problem, order=pp.order, novelty=pp.novelty,
        )
    plan.status = TestPlan.STATUS_STARTED
    plan.save(update_fields=["status"])
    messages.success(request, f"Started assessment for '{plan.name}'.")
    return redirect("tracker:test_detail", pk=test.pk)


def test_plan_skip(request, pk):
    plan = get_object_or_404(TestPlan, pk=pk)
    if request.method == "POST" and plan.status in (TestPlan.STATUS_DRAFT, TestPlan.STATUS_READY):
        plan.status = TestPlan.STATUS_SKIPPED
        plan.save(update_fields=["status"])
    return redirect("tracker:test_plan_list")


def test_plan_discard(request, pk):
    plan = get_object_or_404(TestPlan, pk=pk)
    if request.method == "POST" and plan.status == TestPlan.STATUS_DRAFT:
        plan.delete()
        messages.success(request, "Discarded draft test plan.")
        return redirect("tracker:test_plan_list")
    return redirect("tracker:test_plan_detail", pk=plan.pk)


# ---------------------------------------------------------------------------
# Tests (ad-hoc creation still supported alongside TestPlan-driven ones)
# ---------------------------------------------------------------------------

def test_list(request):
    tests = Test.objects.select_related("test_plan").all()
    return render(request, "tracker/test_list.html", {"tests": tests})


def test_create(request):
    if request.method == "POST":
        form = TestForm(request.POST)
        if form.is_valid():
            test = form.save()
            return redirect("tracker:test_add_problems", pk=test.pk)
    else:
        form = TestForm(initial={"date": timezone.localdate()})
    return render(request, "tracker/test_form.html", {"form": form})


def test_add_problems(request, pk):
    test = get_object_or_404(Test, pk=pk)
    existing_ids = set(test.attempts.values_list("problem_id", flat=True))

    if request.method == "POST":
        selected_ids = request.POST.getlist("problem_id")
        next_order = (
            test.attempts.order_by("-order").values_list("order", flat=True).first() or 0
        ) + 1
        added = 0
        for pid in selected_ids:
            if int(pid) in existing_ids:
                continue
            ProblemAttempt.objects.create(test=test, problem_id=pid, order=next_order)
            next_order += 1
            added += 1
        if added:
            messages.success(request, f"Added {added} problem(s) to {test.name}.")
        return redirect("tracker:test_detail", pk=test.pk)

    problems = Problem.objects.select_related("primary_pattern").exclude(pk__in=existing_ids)
    difficulty = request.GET.get("difficulty", "")
    if difficulty:
        problems = problems.filter(difficulty=difficulty)
    pattern_id = request.GET.get("pattern", "")
    if pattern_id:
        problems = problems.filter(
            Q(primary_pattern_id=pattern_id) | Q(secondary_patterns__id=pattern_id)
        ).distinct()

    return render(request, "tracker/test_add_problems.html", {
        "test": test,
        "problems": problems,
        "patterns": Pattern.objects.all(),
        "difficulty": difficulty,
        "pattern_id": pattern_id,
        "difficulty_choices": Problem.DIFFICULTY_CHOICES,
    })


def test_detail(request, pk):
    test = get_object_or_404(Test, pk=pk)
    attempts = test.attempts.select_related("problem").all()
    summary = analytics.test_summary(test) if test.all_attempts_finished else None
    return render(request, "tracker/test_detail.html", {
        "test": test,
        "attempts": attempts,
        "summary": summary,
    })


def test_complete(request, pk):
    test = get_object_or_404(Test, pk=pk)
    if request.method == "POST" and test.status != Test.STATUS_COMPLETED:
        test.status = Test.STATUS_COMPLETED
        test.completed_at = timezone.now()
        test.save(update_fields=["status", "completed_at"])
        if test.test_plan_id:
            test.test_plan.status = TestPlan.STATUS_COMPLETED
            test.test_plan.save(update_fields=["status"])
        messages.success(request, f"{test.name} marked as completed.")
    return redirect("tracker:test_detail", pk=test.pk)


# ---------------------------------------------------------------------------
# Attempt-focused assessment workflow
# ---------------------------------------------------------------------------

def attempt_detail(request, test_pk, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk, test_id=test_pk)
    plan_problem = None
    if attempt.test.test_plan_id:
        plan_problem = TestPlanProblem.objects.filter(
            test_plan_id=attempt.test.test_plan_id, problem_id=attempt.problem_id
        ).prefetch_related("expected_secondary_patterns", "expected_failure_modes").first()

    sibling_ids = list(attempt.test.attempts.order_by("order").values_list("id", flat=True))
    position = sibling_ids.index(attempt.id) + 1 if attempt.id in sibling_ids else None

    return render(request, "tracker/attempt_detail.html", {
        "attempt": attempt,
        "test": attempt.test,
        "plan_problem": plan_problem,
        "reveal": attempt.is_finished,
        "events": attempt.events.all(),
        "position": position,
        "total": len(sibling_ids),
        "understood": attempt.events.filter(event_type=AttemptEvent.PROBLEM_UNDERSTOOD).exists(),
        "submission_count": analytics.submission_count(attempt),
        "failed_submission_count": analytics.failed_submission_count(attempt),
        "understanding_seconds": analytics.understanding_seconds(attempt),
        "pattern_identification_seconds": analytics.pattern_identification_seconds(attempt),
        "pattern_identified_form": PatternIdentifiedForm(initial={
            "predicted_primary_pattern": attempt.predicted_primary_pattern_id,
            "predicted_secondary_patterns": attempt.predicted_secondary_patterns.all(),
        }),
        "submit_form": SubmitForm(),
        "failure_form": FailureAnalysisForm(),
        "abandon_form": AbandonForm(),
        "test_case_form": TestCaseForm(),
        "pattern_review_form": PatternReviewForm(instance=attempt),
    })


def _bump_test_in_progress(test):
    if test.status == Test.STATUS_CREATED:
        test.status = Test.STATUS_IN_PROGRESS
        test.save(update_fields=["status"])


def attempt_start(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST" and attempt.status == ProblemAttempt.STATUS_NOT_STARTED:
        now = timezone.now()
        attempt.status = ProblemAttempt.STATUS_READING
        attempt.phase_started_at = now
        attempt.started_at = now
        attempt.save()
        AttemptEvent.objects.create(problem_attempt=attempt, event_type=AttemptEvent.PROBLEM_STARTED, timestamp=now)
        _bump_test_in_progress(attempt.test)
    return redirect(attempt.get_absolute_url())


def attempt_understood(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if (request.method == "POST" and attempt.status == ProblemAttempt.STATUS_READING
            and not attempt.events.filter(event_type=AttemptEvent.PROBLEM_UNDERSTOOD).exists()):
        AttemptEvent.objects.create(problem_attempt=attempt, event_type=AttemptEvent.PROBLEM_UNDERSTOOD)
    return redirect(attempt.get_absolute_url())


def attempt_pattern_identified(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST" and attempt.is_active_phase:
        form = PatternIdentifiedForm(request.POST)
        if form.is_valid():
            primary = form.cleaned_data["predicted_primary_pattern"]
            secondary = form.cleaned_data["predicted_secondary_patterns"]
            attempt.predicted_primary_pattern = primary
            attempt.predicted_secondary_patterns.set(secondary)
            attempt.save(update_fields=["predicted_primary_pattern"])
            AttemptEvent.objects.create(
                problem_attempt=attempt, event_type=AttemptEvent.PATTERN_IDENTIFIED,
                metadata={
                    "primary": primary.name if primary else None,
                    "secondary": [p.name for p in secondary],
                },
            )
    return redirect(attempt.get_absolute_url())


def _transition_phase(attempt, new_status, event_type):
    if not attempt.is_active_phase or attempt.status == new_status:
        return
    now = timezone.now()
    attempt.close_current_phase(now)
    attempt.status = new_status
    attempt.phase_started_at = now
    attempt.save()
    AttemptEvent.objects.create(problem_attempt=attempt, event_type=event_type, timestamp=now)


def attempt_start_pseudocode(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST":
        _transition_phase(attempt, ProblemAttempt.STATUS_PSEUDOCODE, AttemptEvent.PSEUDOCODE_STARTED)
    return redirect(attempt.get_absolute_url())


def attempt_start_test_design(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST":
        _transition_phase(attempt, ProblemAttempt.STATUS_TEST_DESIGN, AttemptEvent.TEST_DESIGN_STARTED)
    return redirect(attempt.get_absolute_url())


def attempt_start_implementation(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST":
        _transition_phase(attempt, ProblemAttempt.STATUS_IMPLEMENTATION, AttemptEvent.IMPLEMENTATION_STARTED)
    return redirect(attempt.get_absolute_url())


def attempt_submit(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST" and attempt.is_active_phase:
        form = SubmitForm(request.POST)
        if form.is_valid():
            result = form.cleaned_data["result"]
            confidence = form.cleaned_data.get("confidence") or None
            now = timezone.now()
            AttemptEvent.objects.create(
                problem_attempt=attempt, event_type=AttemptEvent.SUBMITTED,
                timestamp=now, metadata={"result": result},
            )
            if result == "accepted":
                attempt.close_current_phase(now)
                attempt.status = ProblemAttempt.STATUS_COMPLETED
                attempt.solved = True
                attempt.accepted = True
                attempt.first_pass_accepted = not attempt.events.filter(
                    event_type=AttemptEvent.SUBMISSION_FAILED
                ).exists()
                attempt.completed_at = now
                if confidence:
                    attempt.confidence = confidence
                suggested = analytics.suggest_pattern_result(attempt)
                if suggested:
                    attempt.pattern_identification_result = suggested
                attempt.save()
                AttemptEvent.objects.create(problem_attempt=attempt, event_type=AttemptEvent.ACCEPTED, timestamp=now)
            else:
                AttemptEvent.objects.create(
                    problem_attempt=attempt, event_type=AttemptEvent.SUBMISSION_FAILED,
                    timestamp=now, metadata={"result": result},
                )
                if attempt.status != ProblemAttempt.STATUS_DEBUGGING:
                    attempt.close_current_phase(now)
                    attempt.status = ProblemAttempt.STATUS_DEBUGGING
                    attempt.phase_started_at = now
                    attempt.save()
                    AttemptEvent.objects.create(
                        problem_attempt=attempt, event_type=AttemptEvent.DEBUGGING_STARTED, timestamp=now
                    )
    return redirect(attempt.get_absolute_url())


def attempt_add_failure_analysis(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST":
        form = FailureAnalysisForm(request.POST)
        if form.is_valid():
            last_failed = attempt.events.filter(event_type=AttemptEvent.SUBMISSION_FAILED).last()
            submission_number = attempt.events.filter(event_type=AttemptEvent.SUBMITTED).count() or 1
            failure = form.save(commit=False)
            failure.problem_attempt = attempt
            failure.submission_number = submission_number
            failure.result = (last_failed.metadata.get("result") if last_failed else None) or SubmissionFailure.RESULT_OTHER
            failure.save()
    return redirect(attempt.get_absolute_url())


def attempt_abandon(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST" and (attempt.is_active_phase or attempt.status == ProblemAttempt.STATUS_PAUSED):
        form = AbandonForm(request.POST)
        now = timezone.now()
        attempt.close_current_phase(now)
        attempt.status = ProblemAttempt.STATUS_ABANDONED
        attempt.solved = False
        attempt.accepted = False
        attempt.completed_at = now
        if form.is_valid():
            if form.cleaned_data.get("confidence"):
                attempt.confidence = form.cleaned_data["confidence"]
            if form.cleaned_data.get("notes"):
                attempt.notes = form.cleaned_data["notes"]
        suggested = analytics.suggest_pattern_result(attempt)
        if suggested:
            attempt.pattern_identification_result = suggested
        attempt.save()
        AttemptEvent.objects.create(problem_attempt=attempt, event_type=AttemptEvent.ABANDONED, timestamp=now)
    return redirect(attempt.get_absolute_url())


def attempt_pause(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST" and attempt.is_active_phase:
        now = timezone.now()
        paused_from = attempt.status
        attempt.close_current_phase(now)
        attempt.paused_from_status = paused_from
        attempt.status = ProblemAttempt.STATUS_PAUSED
        attempt.save()
        AttemptEvent.objects.create(problem_attempt=attempt, event_type=AttemptEvent.PAUSED, timestamp=now)
    return redirect(attempt.get_absolute_url())


def attempt_resume(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST" and attempt.status == ProblemAttempt.STATUS_PAUSED:
        now = timezone.now()
        attempt.status = attempt.paused_from_status or ProblemAttempt.STATUS_READING
        attempt.paused_from_status = ""
        attempt.phase_started_at = now
        attempt.save()
        AttemptEvent.objects.create(problem_attempt=attempt, event_type=AttemptEvent.RESUMED, timestamp=now)
    return redirect(attempt.get_absolute_url())


def attempt_hint(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST":
        attempt.hints_used += 1
        attempt.save(update_fields=["hints_used"])
    return redirect(attempt.get_absolute_url())


def attempt_pattern_review(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST" and attempt.is_finished:
        form = PatternReviewForm(request.POST, instance=attempt)
        if form.is_valid():
            form.save()
    return redirect(attempt.get_absolute_url())


def attempt_add_test_case(request, pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST":
        form = TestCaseForm(request.POST)
        if form.is_valid():
            test_case = form.save(commit=False)
            test_case.problem_attempt = attempt
            test_case.save()
    return redirect(attempt.get_absolute_url())


def test_case_delete(request, pk, tc_pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST":
        attempt.test_cases.filter(pk=tc_pk).delete()
    return redirect(attempt.get_absolute_url())


def failure_delete(request, pk, f_pk):
    attempt = get_object_or_404(ProblemAttempt, pk=pk)
    if request.method == "POST":
        attempt.failures.filter(pk=f_pk).delete()
    return redirect(attempt.get_absolute_url())


# ---------------------------------------------------------------------------
# CSV exports
# ---------------------------------------------------------------------------

def _csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


def export_tests_csv(request):
    header = ["test_id", "test_plan_id", "test_name", "test_date", "status", "problem_count", "solved_count"]
    rows = [
        [t.id, t.test_plan_id, t.name, t.date, t.status, t.problem_count, t.solved_count]
        for t in Test.objects.all()
    ]
    return _csv_response("tests.csv", header, rows)


def export_problems_csv(request):
    header = ["problem_id", "leetcode_number", "title", "difficulty", "primary_pattern", "leetcode_url"]
    rows = [
        [p.id, p.leetcode_number, p.title, p.difficulty, p.primary_pattern.name, p.leetcode_url]
        for p in Problem.objects.select_related("primary_pattern").all()
    ]
    return _csv_response("problems.csv", header, rows)


ATTEMPT_CSV_HEADER = [
    "test_plan_id", "test_id", "test_date",
    "problem_id", "leetcode_number", "problem_title", "difficulty", "novelty",
    "predicted_pattern", "actual_pattern", "pattern_identification_result",
    "understanding_seconds", "pattern_identification_seconds", "pseudocode_seconds",
    "test_design_seconds", "implementation_seconds", "debugging_seconds",
    "total_active_seconds", "total_wall_clock_seconds", "paused_seconds",
    "hints_used",
    "submission_count", "failed_submissions", "first_pass_accepted",
    "generated_test_cases", "distinct_test_categories", "bug_revealing_test_cases",
    "solved", "accepted", "abandoned",
    "confidence",
]


def _attempt_row(attempt):
    test_cases = list(attempt.test_cases.all())
    actual_pattern = attempt.problem.primary_pattern.name if attempt.problem.primary_pattern_id else ""
    return [
        attempt.test.test_plan_id, attempt.test_id, attempt.test.date,
        attempt.problem_id, attempt.problem.leetcode_number, attempt.problem.title,
        attempt.problem.difficulty, attempt.novelty,
        attempt.predicted_primary_pattern.name if attempt.predicted_primary_pattern_id else "",
        actual_pattern, attempt.pattern_identification_result,
        analytics.understanding_seconds(attempt), analytics.pattern_identification_seconds(attempt),
        attempt.pseudocode_seconds, attempt.test_design_seconds, attempt.implementation_seconds,
        attempt.debugging_seconds,
        attempt.total_active_seconds, attempt.total_wall_clock_seconds, attempt.paused_seconds,
        attempt.hints_used,
        analytics.submission_count(attempt), analytics.failed_submission_count(attempt), attempt.first_pass_accepted,
        len(test_cases), len({tc.category for tc in test_cases}), sum(1 for tc in test_cases if tc.did_find_bug),
        attempt.solved, attempt.accepted, attempt.status == ProblemAttempt.STATUS_ABANDONED,
        attempt.confidence,
    ]


def export_attempts_csv(request):
    attempts = ProblemAttempt.objects.select_related("test", "problem", "predicted_primary_pattern").prefetch_related("test_cases")
    rows = [_attempt_row(a) for a in attempts]
    return _csv_response("attempts.csv", ATTEMPT_CSV_HEADER, rows)


def export_test_attempts_csv(request, pk):
    test = get_object_or_404(Test, pk=pk)
    attempts = test.attempts.select_related("test", "problem", "predicted_primary_pattern").prefetch_related("test_cases")
    rows = [_attempt_row(a) for a in attempts]
    return _csv_response(f"test-{test.pk}-attempts.csv", ATTEMPT_CSV_HEADER, rows)


def export_events_csv(request):
    header = ["event_id", "test_id", "problem_attempt_id", "leetcode_number", "event_type", "timestamp", "metadata"]
    events = AttemptEvent.objects.select_related("problem_attempt__test", "problem_attempt__problem").all()
    rows = [
        [e.id, e.problem_attempt.test_id, e.problem_attempt_id, e.problem_attempt.problem.leetcode_number,
         e.event_type, e.timestamp.isoformat(), e.metadata]
        for e in events
    ]
    return _csv_response("events.csv", header, rows)


def export_test_cases_csv(request):
    header = ["test_id", "problem_attempt_id", "leetcode_number", "category", "description", "expected_behavior", "did_find_bug", "created_at"]
    rows = [
        [tc.problem_attempt.test_id, tc.problem_attempt_id, tc.problem_attempt.problem.leetcode_number,
         tc.category, tc.description, tc.expected_behavior, tc.did_find_bug, tc.created_at.isoformat()]
        for tc in GeneratedTestCase.objects.select_related("problem_attempt__test", "problem_attempt__problem").all()
    ]
    return _csv_response("test-cases.csv", header, rows)


def export_failures_csv(request):
    header = ["test_id", "problem_attempt_id", "leetcode_number", "submission_number", "submission_result", "failure_type", "description", "created_at"]
    rows = [
        [f.problem_attempt.test_id, f.problem_attempt_id, f.problem_attempt.problem.leetcode_number,
         f.submission_number, f.result, f.failure_type, f.description, f.created_at.isoformat()]
        for f in SubmissionFailure.objects.select_related("problem_attempt__test", "problem_attempt__problem").all()
    ]
    return _csv_response("failures.csv", header, rows)
