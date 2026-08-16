from django.db import models
from django.urls import reverse
from django.utils import timezone


class Pattern(models.Model):
    """A reusable algorithmic pattern tag (e.g. Sliding Window, Monotonic Stack)."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Problem(models.Model):
    DIFFICULTY_MEDIUM = "medium"
    DIFFICULTY_HARD = "hard"
    DIFFICULTY_CHOICES = [
        (DIFFICULTY_MEDIUM, "Medium"),
        (DIFFICULTY_HARD, "Hard"),
    ]

    leetcode_number = models.PositiveIntegerField(null=True, blank=True)
    title = models.CharField(max_length=200)
    leetcode_url = models.URLField(blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)
    primary_pattern = models.ForeignKey(
        Pattern, on_delete=models.PROTECT, related_name="primary_problems"
    )
    secondary_patterns = models.ManyToManyField(
        Pattern, blank=True, related_name="secondary_problems"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["leetcode_number", "title"]

    def __str__(self):
        if self.leetcode_number:
            return f"{self.leetcode_number}. {self.title}"
        return self.title

    def get_absolute_url(self):
        return reverse("tracker:problem_edit", args=[self.pk])


NOVELTY_NEVER_SEEN = "never_seen"
NOVELTY_SEEN_NOT_SOLVED = "seen_but_never_solved"
NOVELTY_SOLVED_LONG_AGO = "solved_long_ago"
NOVELTY_RECENTLY_SOLVED = "recently_solved"
NOVELTY_UNKNOWN = "unknown"
NOVELTY_CHOICES = [
    (NOVELTY_NEVER_SEEN, "Never Seen"),
    (NOVELTY_SEEN_NOT_SOLVED, "Seen But Never Solved"),
    (NOVELTY_SOLVED_LONG_AGO, "Solved Long Ago"),
    (NOVELTY_RECENTLY_SOLVED, "Recently Solved"),
    (NOVELTY_UNKNOWN, "Unknown"),
]


# ---------------------------------------------------------------------------
# Test Plans — the curriculum, generated externally (e.g. by ChatGPT) and
# imported as JSON. A TestPlan is what SHOULD be tested; a Test (below) is
# what WAS actually executed.
# ---------------------------------------------------------------------------

class TestPlan(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_READY = "ready"
    STATUS_STARTED = "started"
    STATUS_COMPLETED = "completed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_READY, "Ready"),
        (STATUS_STARTED, "Started"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    scheduled_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    schema_version = models.CharField(max_length=10, default="1.0")
    target_medium = models.PositiveIntegerField(null=True, blank=True)
    target_hard = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("tracker:test_plan_detail", args=[self.pk])

    @property
    def reveal_evaluation(self):
        """Hide the answer key while the plan hasn't finished being assessed."""
        return self.status in (TestPlan.STATUS_COMPLETED, TestPlan.STATUS_SKIPPED)

    @property
    def problem_count(self):
        return self.plan_problems.count()

    @property
    def medium_count(self):
        return self.plan_problems.filter(problem__difficulty=Problem.DIFFICULTY_MEDIUM).count()

    @property
    def hard_count(self):
        return self.plan_problems.filter(problem__difficulty=Problem.DIFFICULTY_HARD).count()


class TestPlanProblem(models.Model):
    test_plan = models.ForeignKey(TestPlan, on_delete=models.CASCADE, related_name="plan_problems")
    problem = models.ForeignKey(Problem, on_delete=models.PROTECT, related_name="plan_appearances")
    order = models.PositiveIntegerField(default=0)
    novelty = models.CharField(max_length=30, choices=NOVELTY_CHOICES, default=NOVELTY_UNKNOWN)

    # Hidden evaluator metadata — the answer key. Never rendered until
    # test_plan.reveal_evaluation (or the individual attempt) allows it.
    selection_reason = models.TextField(blank=True)
    expected_primary_pattern = models.ForeignKey(
        Pattern, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expected_primary_plan_problems",
    )
    expected_secondary_patterns = models.ManyToManyField(
        Pattern, blank=True, related_name="expected_secondary_plan_problems"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["test_plan", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["test_plan", "problem"], name="unique_problem_per_plan"
            ),
        ]

    def __str__(self):
        return f"{self.test_plan} - {self.problem}"


class ExpectedFailureMode(models.Model):
    test_plan_problem = models.ForeignKey(
        TestPlanProblem, on_delete=models.CASCADE, related_name="expected_failure_modes"
    )
    description = models.CharField(max_length=300)

    def __str__(self):
        return self.description


# ---------------------------------------------------------------------------
# Test — an actual execution of a TestPlan (or an ad-hoc assessment created
# directly from the problem catalog, without a plan).
# ---------------------------------------------------------------------------

class Test(models.Model):
    STATUS_CREATED = "created"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_REVIEWED = "reviewed"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REVIEWED, "Reviewed"),
    ]

    test_plan = models.ForeignKey(
        TestPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="tests"
    )
    name = models.CharField(max_length=200)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATED)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("tracker:test_detail", args=[self.pk])

    @property
    def problem_count(self):
        return self.attempts.count()

    @property
    def medium_count(self):
        return self.attempts.filter(problem__difficulty=Problem.DIFFICULTY_MEDIUM).count()

    @property
    def hard_count(self):
        return self.attempts.filter(problem__difficulty=Problem.DIFFICULTY_HARD).count()

    @property
    def solved_count(self):
        return self.attempts.filter(solved=True).count()

    @property
    def all_attempts_finished(self):
        attempts = list(self.attempts.all())
        if not attempts:
            return False
        return all(a.status in (ProblemAttempt.STATUS_COMPLETED, ProblemAttempt.STATUS_ABANDONED) for a in attempts)


class ProblemAttempt(models.Model):
    STATUS_NOT_STARTED = "not_started"
    STATUS_READING = "reading"
    STATUS_PSEUDOCODE = "pseudocode"
    STATUS_TEST_DESIGN = "test_design"
    STATUS_IMPLEMENTATION = "implementation"
    STATUS_DEBUGGING = "debugging"
    STATUS_PAUSED = "paused"
    STATUS_COMPLETED = "completed"
    STATUS_ABANDONED = "abandoned"
    STATUS_CHOICES = [
        (STATUS_NOT_STARTED, "Not Started"),
        (STATUS_READING, "Reading"),
        (STATUS_PSEUDOCODE, "Pseudocode"),
        (STATUS_TEST_DESIGN, "Test Design"),
        (STATUS_IMPLEMENTATION, "Implementation"),
        (STATUS_DEBUGGING, "Hidden-Case Debugging"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_ABANDONED, "Abandoned"),
    ]

    # Phases with their own accumulated-seconds cache field, in workflow order.
    PHASE_FIELD_MAP = {
        STATUS_READING: "reading_seconds",
        STATUS_PSEUDOCODE: "pseudocode_seconds",
        STATUS_TEST_DESIGN: "test_design_seconds",
        STATUS_IMPLEMENTATION: "implementation_seconds",
        STATUS_DEBUGGING: "debugging_seconds",
    }

    PATTERN_RESULT_CORRECT = "correct"
    PATTERN_RESULT_PARTIAL = "partial"
    PATTERN_RESULT_INCORRECT = "incorrect"
    PATTERN_RESULT_NOT_IDENTIFIED = "not_identified"
    PATTERN_RESULT_CHOICES = [
        (PATTERN_RESULT_CORRECT, "Correct"),
        (PATTERN_RESULT_PARTIAL, "Partial"),
        (PATTERN_RESULT_INCORRECT, "Incorrect"),
        (PATTERN_RESULT_NOT_IDENTIFIED, "Not Identified"),
    ]

    CONFIDENCE_CHOICES = [
        (1, "1 - No idea how I would reproduce this"),
        (2, "2 - Weak understanding"),
        (3, "3 - Understand solution"),
        (4, "4 - Could probably reconstruct it"),
        (5, "5 - Could confidently reconstruct it later"),
    ]

    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name="attempts")
    problem = models.ForeignKey(Problem, on_delete=models.PROTECT, related_name="attempts")
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOT_STARTED)

    # Active-phase timer bookkeeping. phase_started_at is null whenever no
    # phase clock is currently running (not started / paused / finished).
    phase_started_at = models.DateTimeField(null=True, blank=True)
    paused_from_status = models.CharField(max_length=20, blank=True)

    # Cached accumulated active seconds per phase (pause-aware). These are a
    # convenience cache — AttemptEvent remains the authoritative record.
    reading_seconds = models.PositiveIntegerField(default=0)
    pseudocode_seconds = models.PositiveIntegerField(default=0)
    test_design_seconds = models.PositiveIntegerField(default=0)
    implementation_seconds = models.PositiveIntegerField(default=0)
    debugging_seconds = models.PositiveIntegerField(default=0)

    novelty = models.CharField(max_length=30, choices=NOVELTY_CHOICES, default=NOVELTY_UNKNOWN)

    predicted_primary_pattern = models.ForeignKey(
        Pattern, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="predicted_primary_attempts",
    )
    predicted_secondary_patterns = models.ManyToManyField(
        Pattern, blank=True, related_name="predicted_secondary_attempts"
    )
    pattern_identification_result = models.CharField(
        max_length=20, choices=PATTERN_RESULT_CHOICES, blank=True
    )

    hints_used = models.PositiveIntegerField(default=0)

    solved = models.BooleanField(default=False)
    accepted = models.BooleanField(default=False)
    first_pass_accepted = models.BooleanField(default=False)

    confidence = models.PositiveSmallIntegerField(null=True, blank=True, choices=CONFIDENCE_CHOICES)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["test", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["test", "problem"], name="unique_problem_per_test"
            ),
        ]

    def __str__(self):
        return f"{self.test} - {self.problem}"

    def get_absolute_url(self):
        return reverse("tracker:attempt_detail", args=[self.test_id, self.pk])

    @property
    def is_active_phase(self):
        return self.status in self.PHASE_FIELD_MAP

    @property
    def is_finished(self):
        return self.status in (self.STATUS_COMPLETED, self.STATUS_ABANDONED)

    @property
    def independent_solve(self):
        return self.solved and self.hints_used == 0

    def close_current_phase(self, at=None):
        """Accumulate elapsed time for the currently running phase, if any."""
        if not self.phase_started_at:
            return
        at = at or timezone.now()
        field = self.PHASE_FIELD_MAP.get(self.status)
        if field:
            elapsed = int((at - self.phase_started_at).total_seconds())
            setattr(self, field, getattr(self, field) + max(elapsed, 0))
        self.phase_started_at = None

    @property
    def current_phase_baseline_seconds(self):
        field = self.PHASE_FIELD_MAP.get(self.status)
        return getattr(self, field) if field else 0

    @property
    def total_active_seconds(self):
        return sum(getattr(self, f) for f in self.PHASE_FIELD_MAP.values())

    @property
    def total_wall_clock_seconds(self):
        if not self.started_at:
            return None
        end = self.completed_at or timezone.now()
        return int((end - self.started_at).total_seconds())

    @property
    def paused_seconds(self):
        total = self.total_wall_clock_seconds
        if total is None:
            return None
        return max(total - self.total_active_seconds, 0)


class AttemptEvent(models.Model):
    PROBLEM_STARTED = "PROBLEM_STARTED"
    PROBLEM_UNDERSTOOD = "PROBLEM_UNDERSTOOD"
    PATTERN_IDENTIFIED = "PATTERN_IDENTIFIED"
    PSEUDOCODE_STARTED = "PSEUDOCODE_STARTED"
    TEST_DESIGN_STARTED = "TEST_DESIGN_STARTED"
    IMPLEMENTATION_STARTED = "IMPLEMENTATION_STARTED"
    SUBMITTED = "SUBMITTED"
    SUBMISSION_FAILED = "SUBMISSION_FAILED"
    DEBUGGING_STARTED = "DEBUGGING_STARTED"
    ACCEPTED = "ACCEPTED"
    ABANDONED = "ABANDONED"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    EVENT_TYPE_CHOICES = [
        (PROBLEM_STARTED, "Problem Started"),
        (PROBLEM_UNDERSTOOD, "Problem Understood"),
        (PATTERN_IDENTIFIED, "Pattern Identified"),
        (PSEUDOCODE_STARTED, "Pseudocode Started"),
        (TEST_DESIGN_STARTED, "Test Design Started"),
        (IMPLEMENTATION_STARTED, "Implementation Started"),
        (SUBMITTED, "Submitted"),
        (SUBMISSION_FAILED, "Submission Failed"),
        (DEBUGGING_STARTED, "Debugging Started"),
        (ACCEPTED, "Accepted"),
        (ABANDONED, "Abandoned"),
        (PAUSED, "Paused"),
        (RESUMED, "Resumed"),
    ]

    problem_attempt = models.ForeignKey(ProblemAttempt, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    timestamp = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["timestamp", "id"]

    def __str__(self):
        return f"{self.problem_attempt} @ {self.timestamp:%H:%M:%S} - {self.event_type}"


class GeneratedTestCase(models.Model):
    CATEGORY_CHOICES = [
        ("basic", "Basic"),
        ("minimum_input", "Minimum Input"),
        ("maximum_input", "Maximum Input"),
        ("boundary", "Boundary"),
        ("increasing", "Increasing"),
        ("decreasing", "Decreasing"),
        ("duplicates", "Duplicates"),
        ("all_equal", "All Equal"),
        ("alternating", "Alternating"),
        ("negative_values", "Negative Values"),
        ("overflow", "Overflow"),
        ("off_by_one", "Off-by-One"),
        ("adversarial", "Adversarial"),
        ("custom", "Custom"),
    ]

    problem_attempt = models.ForeignKey(
        ProblemAttempt, on_delete=models.CASCADE, related_name="test_cases"
    )
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    description = models.CharField(max_length=500)
    expected_behavior = models.CharField(max_length=500, blank=True)
    did_find_bug = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_category_display()}: {self.description[:40]}"


class SubmissionFailure(models.Model):
    RESULT_WRONG_ANSWER = "wrong_answer"
    RESULT_TLE = "tle"
    RESULT_MLE = "mle"
    RESULT_RUNTIME_ERROR = "runtime_error"
    RESULT_OTHER = "other"
    RESULT_CHOICES = [
        (RESULT_WRONG_ANSWER, "Wrong Answer"),
        (RESULT_TLE, "TLE"),
        (RESULT_MLE, "MLE"),
        (RESULT_RUNTIME_ERROR, "Runtime Error"),
        (RESULT_OTHER, "Other"),
    ]

    FAILURE_TYPE_CHOICES = [
        ("wrong_algorithm", "Wrong Algorithm"),
        ("incorrect_pattern", "Incorrect Pattern"),
        ("logic_error", "Logic Error"),
        ("implementation_error", "Implementation Error"),
        ("edge_case", "Edge Case"),
        ("off_by_one", "Off-by-One"),
        ("complexity_tle", "Complexity / TLE"),
        ("memory_limit", "Memory Limit"),
        ("misread_problem", "Misread Problem"),
        ("incorrect_data_structure", "Incorrect Data Structure"),
        ("language_syntax", "Language / Syntax"),
        ("other", "Other"),
    ]

    problem_attempt = models.ForeignKey(
        ProblemAttempt, on_delete=models.CASCADE, related_name="failures"
    )
    submission_number = models.PositiveIntegerField()
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)
    failure_type = models.CharField(max_length=30, choices=FAILURE_TYPE_CHOICES, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"#{self.submission_number} {self.get_result_display()}"
