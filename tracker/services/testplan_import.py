"""Validation and import of TestPlan JSON files (the ChatGPT <-> LMS contract).

Two-step process:
  validate(data)  -> (errors, warnings)   -- pure, no DB writes
  import_plan(data) -> TestPlan           -- only called once validate() has no errors
"""
from django.db import transaction
from django.utils import timezone

from tracker.models import (
    ExpectedFailureMode,
    Pattern,
    Problem,
    TestPlan,
    TestPlanProblem,
)

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}

_NOVELTY_LOOKUP = {
    "never seen": "never_seen",
    "seen but never solved": "seen_but_never_solved",
    "solved long ago": "solved_long_ago",
    "recently solved": "recently_solved",
    "unknown": "unknown",
}


def validate(data):
    """Returns (errors, warnings, medium_hard_counts). Does not touch the DB."""
    errors = []
    warnings = []

    if not isinstance(data, dict):
        return ["Top-level JSON must be an object."], [], (0, 0)

    schema_version = data.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(
            f"Unsupported or missing schema_version: {schema_version!r} "
            f"(supported: {', '.join(sorted(SUPPORTED_SCHEMA_VERSIONS))})."
        )

    if not data.get("name"):
        errors.append("Missing required field: name")

    problems = data.get("problems")
    if not isinstance(problems, list) or not problems:
        errors.append("Missing or empty required field: problems (must be a non-empty array)")
        problems = []

    seen_numbers = set()
    seen_orders = set()
    medium_count = 0
    hard_count = 0

    for i, p in enumerate(problems):
        prefix = f"Problem #{i + 1}"
        if not isinstance(p, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        title = p.get("title")
        if not title:
            errors.append(f"{prefix}: missing title")
        label = title or "?"

        leetcode_number = p.get("leetcode_number")
        if not leetcode_number:
            errors.append(f"{prefix} ({label}): missing leetcode_number")
        elif leetcode_number in seen_numbers:
            errors.append(f"{prefix} ({label}): duplicate leetcode_number {leetcode_number} within this plan")
        else:
            seen_numbers.add(leetcode_number)

        difficulty_raw = str(p.get("difficulty") or "").strip().lower()
        if difficulty_raw not in ("medium", "hard"):
            errors.append(f"{prefix} ({label}): invalid difficulty {p.get('difficulty')!r} (must be Medium or Hard)")
        elif difficulty_raw == "medium":
            medium_count += 1
        else:
            hard_count += 1

        order = p.get("order")
        if order is None:
            errors.append(f"{prefix} ({label}): missing order")
        elif order in seen_orders:
            errors.append(f"{prefix} ({label}): duplicate order value {order}")
        else:
            seen_orders.add(order)

        novelty_raw = p.get("novelty")
        if novelty_raw and novelty_raw.strip().lower() not in _NOVELTY_LOOKUP:
            warnings.append(f"{prefix} ({label}): unrecognized novelty {novelty_raw!r}, will store as Unknown")

    if not errors:
        total = medium_count + hard_count
        if total:
            target = data.get("target_distribution") or {}
            target_medium = target.get("medium")
            target_hard = target.get("hard")
            if target_medium is not None and target_hard is not None and (target_medium + target_hard) > 0:
                target_pct_medium = target_medium / (target_medium + target_hard) * 100
            else:
                target_pct_medium = 80
            actual_pct_medium = medium_count / total * 100
            if abs(actual_pct_medium - target_pct_medium) > 20:
                warnings.append(
                    f"Distribution is {medium_count} Medium / {hard_count} Hard "
                    f"({actual_pct_medium:.0f}% medium) — target is ~{target_pct_medium:.0f}% medium."
                )

    return errors, warnings, (medium_count, hard_count)


def _get_pattern(name):
    name = (name or "").strip()
    if not name:
        return None
    pattern, _ = Pattern.objects.get_or_create(name=name)
    return pattern


def _resolve_problem(entry):
    leetcode_number = entry["leetcode_number"]
    difficulty = str(entry["difficulty"]).strip().lower()
    evaluation = entry.get("evaluation") or {}
    primary_pattern_name = evaluation.get("primary_pattern")

    problem = Problem.objects.filter(leetcode_number=leetcode_number).first()
    if problem:
        return problem

    primary_pattern = _get_pattern(primary_pattern_name) if primary_pattern_name else _get_pattern("Uncategorized")
    problem = Problem.objects.create(
        leetcode_number=leetcode_number,
        title=entry["title"],
        leetcode_url=entry.get("url", ""),
        difficulty=difficulty,
        primary_pattern=primary_pattern,
    )
    for name in evaluation.get("secondary_patterns") or []:
        problem.secondary_patterns.add(_get_pattern(name))
    return problem


@transaction.atomic
def import_plan(data):
    target = data.get("target_distribution") or {}
    plan = TestPlan.objects.create(
        name=data["name"],
        description=data.get("description", ""),
        schema_version=data.get("schema_version", "1.0"),
        target_medium=target.get("medium"),
        target_hard=target.get("hard"),
        imported_at=timezone.now(),
        status=TestPlan.STATUS_DRAFT,
    )

    for entry in sorted(data["problems"], key=lambda p: p.get("order", 0)):
        problem = _resolve_problem(entry)
        evaluation = entry.get("evaluation") or {}
        novelty = _NOVELTY_LOOKUP.get(str(entry.get("novelty") or "").strip().lower(), "unknown")

        plan_problem = TestPlanProblem.objects.create(
            test_plan=plan,
            problem=problem,
            order=entry.get("order", 0),
            novelty=novelty,
            selection_reason=evaluation.get("selection_reason", ""),
            expected_primary_pattern=_get_pattern(evaluation.get("primary_pattern")),
        )
        for name in evaluation.get("secondary_patterns") or []:
            pattern = _get_pattern(name)
            if pattern:
                plan_problem.expected_secondary_patterns.add(pattern)
        for description in evaluation.get("expected_failure_modes") or []:
            ExpectedFailureMode.objects.create(test_plan_problem=plan_problem, description=description)

    return plan
