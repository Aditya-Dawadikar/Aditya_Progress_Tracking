"""Derived metrics computed from the raw AttemptEvent timeline and cached
ProblemAttempt fields. Raw events remain authoritative; everything here is
read-only derivation, safe to recompute or change without touching history.
"""
import statistics

from tracker.models import AttemptEvent, ProblemAttempt


def _event_at(attempt, event_type, last=False):
    qs = attempt.events.filter(event_type=event_type)
    ev = qs.last() if last else qs.first()
    return ev.timestamp if ev else None


def understanding_seconds(attempt):
    started = _event_at(attempt, AttemptEvent.PROBLEM_STARTED)
    understood = _event_at(attempt, AttemptEvent.PROBLEM_UNDERSTOOD)
    if started and understood:
        return int((understood - started).total_seconds())
    return None


def pattern_identification_seconds(attempt):
    started = _event_at(attempt, AttemptEvent.PROBLEM_STARTED)
    identified = _event_at(attempt, AttemptEvent.PATTERN_IDENTIFIED)
    if started and identified:
        return int((identified - started).total_seconds())
    return None


def submission_count(attempt):
    return attempt.events.filter(event_type=AttemptEvent.SUBMITTED).count()


def failed_submission_count(attempt):
    return attempt.events.filter(event_type=AttemptEvent.SUBMISSION_FAILED).count()


def median_seconds(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return statistics.median(values)


def test_summary(test):
    attempts = list(test.attempts.all())
    finished = [a for a in attempts if a.is_finished]
    solved = [a for a in attempts if a.solved]
    independent = [a for a in attempts if a.independent_solve]
    with_prediction = [a for a in attempts if a.pattern_identification_result]
    correct = [a for a in with_prediction if a.pattern_identification_result == ProblemAttempt.PATTERN_RESULT_CORRECT]
    first_pass = [a for a in solved if a.first_pass_accepted]

    test_cases = []
    bug_revealing = 0
    categories = set()
    for a in attempts:
        for tc in a.test_cases.all():
            test_cases.append(tc)
            categories.add(tc.category)
            if tc.did_find_bug:
                bug_revealing += 1

    return {
        "problem_count": len(attempts),
        "finished_count": len(finished),
        "solved_count": len(solved),
        "independent_solve_count": len(independent),
        "pattern_recognition_pct": round(len(correct) / len(with_prediction) * 100) if with_prediction else None,
        "first_pass_pct": round(len(first_pass) / len(solved) * 100) if solved else None,
        "median_understanding": median_seconds([understanding_seconds(a) for a in attempts]),
        "median_pattern_identification": median_seconds([pattern_identification_seconds(a) for a in attempts]),
        "median_pseudocode": median_seconds([a.pseudocode_seconds for a in attempts if a.pseudocode_seconds]),
        "median_test_design": median_seconds([a.test_design_seconds for a in attempts if a.test_design_seconds]),
        "median_implementation": median_seconds([a.implementation_seconds for a in attempts if a.implementation_seconds]),
        "median_debugging": median_seconds([a.debugging_seconds for a in attempts if a.debugging_seconds]),
        "test_cases_generated": len(test_cases),
        "distinct_test_categories": len(categories),
        "bug_revealing_test_cases": bug_revealing,
    }


def suggest_pattern_result(attempt):
    """Auto-classify predicted vs. expected pattern, if an answer key exists."""
    plan_problem = None
    if attempt.test.test_plan_id:
        plan_problem = attempt.test.test_plan.plan_problems.filter(problem_id=attempt.problem_id).first()

    if not plan_problem or not plan_problem.expected_primary_pattern_id:
        return attempt.pattern_identification_result or ""

    if not attempt.predicted_primary_pattern_id:
        return ProblemAttempt.PATTERN_RESULT_NOT_IDENTIFIED

    expected_secondary_ids = set(plan_problem.expected_secondary_patterns.values_list("id", flat=True))
    predicted_secondary_ids = set(attempt.predicted_secondary_patterns.values_list("id", flat=True))

    if attempt.predicted_primary_pattern_id == plan_problem.expected_primary_pattern_id:
        return ProblemAttempt.PATTERN_RESULT_CORRECT
    if (
        attempt.predicted_primary_pattern_id in expected_secondary_ids
        or plan_problem.expected_primary_pattern_id in predicted_secondary_ids
    ):
        return ProblemAttempt.PATTERN_RESULT_PARTIAL
    return ProblemAttempt.PATTERN_RESULT_INCORRECT
