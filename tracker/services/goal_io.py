"""JSON export/import for bulk-transferring a board's goals.

Export produces a tree matching the shape import expects, so a board's
goals.json can be downloaded and re-imported (into the same board, a
different board, or a different deployment entirely) without hand-editing.
"""
import itertools

from django.core.exceptions import ValidationError
from django.db import transaction

from tracker.models import CATEGORY_PALETTE, Category, Goal, Member

SCHEMA_VERSION = "1.0"
VALID_STATUSES = dict(Goal.STATUS_CHOICES)


def _serialize_goal(goal):
    return {
        "title": goal.title,
        "description": goal.description,
        "category": goal.category.name if goal.category_id else None,
        "owner": goal.owner.name,
        "status": goal.status,
        "start_date": goal.start_date.isoformat() if goal.start_date else None,
        "end_date": goal.end_date.isoformat() if goal.end_date else None,
        "progress_percent": goal.progress_percent,
        "subgoals": [_serialize_goal(child) for child in goal.subgoals.all()],
    }


def export_board(board):
    top_level = board.top_level_goals.select_related("owner", "category").prefetch_related("subgoals")
    return {
        "schema_version": SCHEMA_VERSION,
        "board": {"name": board.name, "description": board.description},
        "goals": [_serialize_goal(goal) for goal in top_level],
    }


class GoalImportError(Exception):
    """Raised with a list of human-readable validation errors."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _validate_node(node, path, errors):
    if not isinstance(node, dict):
        errors.append(f"{path}: must be an object")
        return
    title = node.get("title")
    if not title or not isinstance(title, str):
        errors.append(f"{path}.title: required")
    status = node.get("status") or Goal.STATUS_NOT_STARTED
    if status not in VALID_STATUSES:
        errors.append(f"{path}.status: '{status}' is not a valid status")
    progress = node.get("progress_percent", 0)
    if progress is not None and not isinstance(progress, int):
        errors.append(f"{path}.progress_percent: must be an integer")
    elif progress is not None and not (0 <= progress <= 100):
        errors.append(f"{path}.progress_percent: must be between 0 and 100")
    for field in ("start_date", "end_date"):
        value = node.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"{path}.{field}: must be an ISO date string or null")
    for i, child in enumerate(node.get("subgoals") or []):
        _validate_node(child, f"{path}.subgoals[{i}]", errors)


def validate_import(data):
    errors = []
    if not isinstance(data, dict):
        errors.append("root: must be a JSON object")
        return errors
    goals = data.get("goals")
    if not isinstance(goals, list):
        errors.append("goals: must be a list")
        return errors
    for i, node in enumerate(goals):
        _validate_node(node, f"goals[{i}]", errors)
    return errors


_palette_cycle = itertools.cycle([hex_ for hex_, _ in CATEGORY_PALETTE])


def _get_category(name, cache):
    if not name:
        return None
    key = name.strip().lower()
    if key in cache:
        return cache[key]
    category, _ = Category.objects.get_or_create(
        name__iexact=name.strip(),
        defaults={"name": name.strip(), "color": next(_palette_cycle)},
    )
    cache[key] = category
    return category


def _get_member(name, cache, fallback):
    if not name:
        return fallback
    key = name.strip().lower()
    if key in cache:
        return cache[key]
    member, _ = Member.objects.get_or_create(name__iexact=name.strip(), defaults={"name": name.strip()})
    cache[key] = member
    return member


def _create_goal(node, board, parent, default_owner, category_cache, member_cache):
    goal = Goal(
        board=board,
        parent=parent,
        owner=_get_member(node.get("owner"), member_cache, default_owner),
        title=node["title"].strip(),
        description=node.get("description") or "",
        category=_get_category(node.get("category"), category_cache),
        status=node.get("status") or Goal.STATUS_NOT_STARTED,
        start_date=node.get("start_date") or None,
        end_date=node.get("end_date") or None,
        progress_percent=node.get("progress_percent") or 0,
        order=Goal.objects.filter(parent=parent, board=board).count(),
    )
    goal.full_clean(exclude=["board"])
    goal.save()
    for child in node.get("subgoals") or []:
        _create_goal(child, board, goal, default_owner, category_cache, member_cache)
    return goal


def import_goals(board, data, default_owner):
    """Validate then create the goal tree from `data` under `board`.

    Raises GoalImportError with a list of errors and creates nothing if the
    document is invalid. Returns the count of goals created (including
    subgoals) on success.
    """
    errors = validate_import(data)
    if errors:
        raise GoalImportError(errors)

    category_cache, member_cache = {}, {}
    created = 0
    with transaction.atomic():
        for node in data["goals"]:
            try:
                _create_goal(node, board, None, default_owner, category_cache, member_cache)
            except ValidationError as exc:
                raise GoalImportError([str(exc)])
            created += 1 + _count_subgoals(node)
    return created


def _count_subgoals(node):
    return sum(1 + _count_subgoals(child) for child in node.get("subgoals") or [])
