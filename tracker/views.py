import json
from functools import wraps

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import BoardFilterForm, CategoryForm, GoalBoardForm, GoalForm, GoalImportForm, MemberForm, TodoTaskForm
from .models import Category, Goal, GoalBoard, Member, TodoTask
from .services import goal_io
from .services.scoring import member_leaderboard


def require_member(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.member is None:
            messages.info(request, "Pick a name to do that.")
            return redirect(f"{reverse('tracker:whoami')}?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)
    return wrapper


def safe_next_url(request, raw_next):
    if raw_next and url_has_allowed_host_and_scheme(
        raw_next, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return raw_next
    return reverse("tracker:boards_list")


def group_by_status(goals):
    goals = sorted(goals, key=lambda g: g.order)
    buckets = {key: [] for key, _ in Goal.STATUS_CHOICES}
    for g in goals:
        buckets[g.status].append(g)
    return [
        {"key": key, "label": label, "goals": buckets[key]}
        for key, label in Goal.STATUS_CHOICES
    ]


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def whoami(request):
    next_url = safe_next_url(request, request.GET.get("next") or request.POST.get("next"))
    if request.method == "POST":
        if request.POST.get("action") == "switch":
            member = get_object_or_404(Member, pk=request.POST.get("member_id"))
            request.session["member_id"] = str(member.pk)
            messages.success(request, f"You're now {member.name}.")
            return redirect(next_url)

        form = MemberForm(request.POST)
        if form.is_valid():
            member = form.save()
            request.session["member_id"] = str(member.pk)
            messages.success(request, f"Welcome, {member.name}.")
            return redirect(next_url)
    else:
        form = MemberForm()

    return render(request, "tracker/whoami.html", {
        "form": form,
        "members": Member.objects.all(),
        "next": next_url,
    })


def whoami_logout(request):
    request.session.pop("member_id", None)
    messages.info(request, "Signed out.")
    return redirect(safe_next_url(request, request.GET.get("next")))


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@require_member
def category_list(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.member
            category.save()
            messages.success(request, f"Category “{category.name}” created.")
            return redirect("tracker:category_list")
    else:
        form = CategoryForm()
    return render(request, "tracker/categories.html", {
        "form": form,
        "categories": Category.objects.all(),
    })


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------

def boards_list(request):
    boards = GoalBoard.objects.all()
    for board in boards:
        top_level = list(board.top_level_goals)
        board.goal_count = len(top_level)
        board.avg_progress = (
            round(sum(g.effective_progress for g in top_level) / len(top_level))
            if top_level else None
        )
    return render(request, "tracker/boards_list.html", {"boards": boards})


@require_member
def board_create(request):
    if request.method == "POST":
        form = GoalBoardForm(request.POST)
        if form.is_valid():
            board = form.save(commit=False)
            board.created_by = request.member
            board.save()
            messages.success(request, f"Board “{board.name}” created.")
            return redirect(board.get_absolute_url())
    else:
        form = GoalBoardForm()
    return render(request, "tracker/board_form.html", {"form": form, "is_new": True})


def board_detail(request, pk):
    board = get_object_or_404(GoalBoard, pk=pk)
    goals_qs = board.top_level_goals.select_related("owner", "category")

    filter_form = BoardFilterForm(request.GET or None, goals_queryset=goals_qs)
    if filter_form.is_valid():
        cd = filter_form.cleaned_data
        if cd["q"]:
            goals_qs = goals_qs.filter(Q(title__icontains=cd["q"]) | Q(description__icontains=cd["q"]))
        if cd["category"]:
            goals_qs = goals_qs.filter(category=cd["category"])
        if cd["owner"]:
            goals_qs = goals_qs.filter(owner=cd["owner"])
        if cd["start_after"]:
            goals_qs = goals_qs.filter(start_date__gte=cd["start_after"])
        if cd["end_before"]:
            goals_qs = goals_qs.filter(end_date__lte=cd["end_before"])

    return render(request, "tracker/board_detail.html", {
        "board": board,
        "columns": group_by_status(list(goals_qs)),
        "reorder_scope": "board",
        "reorder_scope_id": board.pk,
        "filter_form": filter_form,
        "filters_active": any(request.GET.get(f) for f in ("q", "category", "owner", "start_after", "end_before")),
    })


@require_member
def board_edit(request, pk):
    board = get_object_or_404(GoalBoard, pk=pk)
    if board.created_by_id != request.member.pk:
        messages.error(request, "Only the board's creator can edit it.")
        return redirect(board.get_absolute_url())
    if request.method == "POST":
        form = GoalBoardForm(request.POST, instance=board)
        if form.is_valid():
            form.save()
            messages.success(request, "Board updated.")
            return redirect(board.get_absolute_url())
    else:
        form = GoalBoardForm(instance=board)
    return render(request, "tracker/board_form.html", {"form": form, "board": board, "is_new": False})


@require_member
def board_delete(request, pk):
    board = get_object_or_404(GoalBoard, pk=pk)
    if board.created_by_id != request.member.pk:
        messages.error(request, "Only the board's creator can delete it.")
        return redirect(board.get_absolute_url())
    if request.method == "POST":
        board.delete()
        messages.success(request, f"Board “{board.name}” deleted.")
        return redirect("tracker:boards_list")
    return render(request, "tracker/board_confirm_delete.html", {"board": board})


def board_export_json(request, pk):
    board = get_object_or_404(GoalBoard, pk=pk)
    data = goal_io.export_board(board)
    response = HttpResponse(json.dumps(data, indent=2), content_type="application/json")
    filename = f"{board.name.strip().replace(' ', '_').lower() or 'board'}-goals.json"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_member
def board_import_json(request, pk):
    board = get_object_or_404(GoalBoard, pk=pk)
    errors = []
    if request.method == "POST":
        form = GoalImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                raw = form.cleaned_data["file"].read().decode("utf-8")
                data = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors = [f"Not valid JSON: {exc}"]
            else:
                try:
                    created = goal_io.import_goals(board, data, default_owner=request.member)
                except goal_io.GoalImportError as exc:
                    errors = exc.errors
                else:
                    messages.success(request, f"Imported {created} goal(s).")
                    return redirect(board.get_absolute_url())
    else:
        form = GoalImportForm()
    return render(request, "tracker/board_import.html", {"board": board, "form": form, "errors": errors})


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

@require_member
def goal_create(request):
    board_id = request.GET.get("board") or request.POST.get("board")
    if not board_id:
        return HttpResponseBadRequest("A board is required.")
    board = get_object_or_404(GoalBoard, pk=board_id)

    if request.method == "POST":
        form = GoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.board = board
            goal.owner = request.member
            goal.order = Goal.objects.filter(board=board).count()
            try:
                goal.full_clean(exclude=["board"])
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                goal.save()
                messages.success(request, f"Goal “{goal.title}” created.")
                return redirect(board.get_absolute_url())
    else:
        form = GoalForm()

    return render(request, "tracker/goal_form.html", {
        "form": form, "board": board, "is_new": True,
    })


def goal_detail(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    return render(request, "tracker/goal_detail.html", {
        "goal": goal,
        "task_form": TodoTaskForm(),
    })


@require_member
def goal_edit(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    if goal.owner_id != request.member.pk:
        messages.error(request, "Only the goal's owner can edit it.")
        return redirect(goal.get_absolute_url())
    if request.method == "POST":
        form = GoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            messages.success(request, "Goal updated.")
            return redirect(goal.get_absolute_url())
    else:
        form = GoalForm(instance=goal)
    return render(request, "tracker/goal_form.html", {
        "form": form, "goal": goal, "board": goal.board, "is_new": False,
    })


@require_member
def goal_delete(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    if goal.owner_id != request.member.pk:
        messages.error(request, "Only the goal's owner can delete it.")
        return redirect(goal.get_absolute_url())
    redirect_to = goal.board.get_absolute_url()
    if request.method == "POST":
        title = goal.title
        goal.delete()
        messages.success(request, f"Goal “{title}” deleted.")
        return redirect(redirect_to)
    return render(request, "tracker/goal_confirm_delete.html", {"goal": goal})


@require_member
@require_POST
def goal_reorder(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    scope = data.get("scope")
    scope_id = data.get("scope_id")
    columns = data.get("columns", {})
    valid_statuses = dict(Goal.STATUS_CHOICES)

    if scope != "board":
        return HttpResponseBadRequest("Unknown scope")
    base_qs = Goal.objects.filter(board_id=scope_id)

    # Only the goals the caller owns may actually be moved/reordered — a
    # shared board can hold other members' cards too, but dragging one
    # can't change another member's status/order (that'd let anyone flip
    # someone else's goal to "completed"/"abandoned" and skew their score).
    valid_ids = set(base_qs.filter(owner=request.member).values_list("id", flat=True))

    with transaction.atomic():
        for status, ids in columns.items():
            if status not in valid_statuses:
                continue
            for index, raw_id in enumerate(ids):
                try:
                    gid = Goal._meta.pk.to_python(raw_id)
                except (TypeError, ValueError, ValidationError):
                    continue
                if gid not in valid_ids:
                    continue
                goal = Goal.objects.get(pk=gid)
                if goal.status != status or goal.order != index:
                    goal.status = status
                    goal.order = index
                    goal.save()

    return JsonResponse({"ok": True})


@require_member
@require_POST
def task_create(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    if goal.owner_id != request.member.pk:
        return redirect(goal.get_absolute_url())
    form = TodoTaskForm(request.POST)
    if form.is_valid():
        task = form.save(commit=False)
        task.goal = goal
        task.order = goal.tasks.count()
        task.save()
        messages.success(request, "Task added.")
    return redirect(goal.get_absolute_url())


@require_member
@require_POST
def task_toggle(request, pk):
    task = get_object_or_404(TodoTask, pk=pk)
    if task.goal.owner_id == request.member.pk:
        task.completed = not task.completed
        task.save(update_fields=["completed"])
    return redirect(task.goal.get_absolute_url())


@require_member
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(TodoTask, pk=pk)
    goal = task.goal
    if goal.owner_id == request.member.pk:
        task.delete()
        messages.success(request, "Task deleted.")
    return redirect(goal.get_absolute_url())


# ---------------------------------------------------------------------------
# Leaderboard / profiles
# ---------------------------------------------------------------------------

def leaderboard(request):
    return render(request, "tracker/leaderboard.html", {"members": member_leaderboard()})


def member_profile(request, slug):
    member = get_object_or_404(Member, slug=slug)
    top_level = list(member.goals.select_related("board", "category"))
    return render(request, "tracker/member_profile.html", {"member": member, "goals": top_level})
