"""JSON export/import for boards and their non-nestable goal tasks."""
import itertools

from django.core.exceptions import ValidationError
from django.db import transaction

from tracker.models import CATEGORY_PALETTE, Category, Goal

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
        "tasks": [
            {
                "title": task.title,
                "completed": task.completed,
                "due_date": task.due_date.isoformat() if task.due_date else None,
            }
            for task in goal.tasks.all()
        ],
    }


def export_board(board):
    top_level = board.top_level_goals.select_related("owner", "category").prefetch_related("tasks")
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
    tasks = node.get("tasks") or []
    if not isinstance(tasks, list):
        errors.append(f"{path}.tasks: must be a list")
    for i, task in enumerate(tasks):
        if not isinstance(task, dict) or not isinstance(task.get("title"), str) or not task["title"].strip():
            errors.append(f"{path}.tasks[{i}].title: required")
        elif not isinstance(task.get("completed", False), bool):
            errors.append(f"{path}.tasks[{i}].completed: must be true or false")
        elif task.get("due_date") is not None and not isinstance(task["due_date"], str):
            errors.append(f"{path}.tasks[{i}].due_date: must be an ISO date string or null")


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


def _get_category(board, name, cache):
    if not name:
        return None
    key = name.strip().lower()
    if key in cache:
        return cache[key]
    category, _ = Category.objects.get_or_create(
        board=board,
        name=name.strip(),
        defaults={"name": name.strip(), "color": next(_palette_cycle)},
    )
    cache[key] = category
    return category


def _create_goal(node, board, default_owner, category_cache):
    # Every imported goal is owned by whoever is running the import — never
    # by an `owner` name taken from the file itself. Otherwise anyone could
    # craft a JSON file naming a real member as "owner" of fabricated goals
    # and pollute that member's profile/leaderboard score without their
    # involvement (the same rule goal_create/goal_reorder already enforce).
    goal = Goal(
        board=board,
        owner=default_owner,
        title=node["title"].strip(),
        description=node.get("description") or "",
        category=_get_category(board, node.get("category"), category_cache),
        status=node.get("status") or Goal.STATUS_NOT_STARTED,
        start_date=node.get("start_date") or None,
        end_date=node.get("end_date") or None,
        progress_percent=node.get("progress_percent") or 0,
        order=Goal.objects.filter(board=board).count(),
    )
    goal.full_clean(exclude=["board"])
    goal.save()
    for order, task_data in enumerate(node.get("tasks") or []):
        goal.tasks.create(
            title=task_data["title"].strip(),
            completed=task_data.get("completed", False),
            due_date=task_data.get("due_date") or None,
            order=order,
        )
    return goal


def import_goals(board, data, default_owner):
    """Validate then create the goal tree from `data` under `board`, all
    owned by `default_owner` (see _create_goal for why).

    Raises GoalImportError with a list of errors and creates nothing if the
    document is invalid. Returns the count of goals created on success.
    """
    errors = validate_import(data)
    if errors:
        raise GoalImportError(errors)

    category_cache = {}
    created = 0
    with transaction.atomic():
        for node in data["goals"]:
            try:
                _create_goal(node, board, default_owner, category_cache)
            except ValidationError as exc:
                raise GoalImportError([str(exc)])
            created += 1
    return created
