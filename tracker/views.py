import json
from functools import wraps

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import GoalBoardForm, GoalForm, MemberForm
from .models import Goal, GoalBoard, Member
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
            request.session["member_id"] = member.pk
            messages.success(request, f"You're now {member.name}.")
            return redirect(next_url)

        form = MemberForm(request.POST)
        if form.is_valid():
            member = form.save()
            request.session["member_id"] = member.pk
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
    top_level = list(board.top_level_goals.select_related("owner"))
    return render(request, "tracker/board_detail.html", {
        "board": board,
        "columns": group_by_status(top_level),
        "reorder_scope": "board",
        "reorder_scope_id": board.pk,
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


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

@require_member
def goal_create(request):
    board = None
    parent = None
    board_id = request.GET.get("board") or request.POST.get("board")
    parent_id = request.GET.get("parent") or request.POST.get("parent")
    if parent_id:
        parent = get_object_or_404(Goal, pk=parent_id)
        board = parent.board
    elif board_id:
        board = get_object_or_404(GoalBoard, pk=board_id)
    else:
        return HttpResponseBadRequest("A board or parent goal is required.")

    if request.method == "POST":
        form = GoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.board = board
            goal.parent = parent
            goal.owner = request.member
            goal.order = Goal.objects.filter(parent=parent, board=board).count()
            try:
                goal.full_clean(exclude=["board"])
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                goal.save()
                messages.success(request, f"Goal “{goal.title}” created.")
                return redirect(goal.get_absolute_url() if parent else board.get_absolute_url())
    else:
        form = GoalForm()

    return render(request, "tracker/goal_form.html", {
        "form": form, "board": board, "parent": parent, "is_new": True,
    })


def goal_detail(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    subgoals = list(goal.subgoals.select_related("owner"))
    return render(request, "tracker/goal_detail.html", {
        "goal": goal,
        "columns": group_by_status(subgoals),
        "reorder_scope": "parent",
        "reorder_scope_id": goal.pk,
    })


@require_member
def goal_edit(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    if goal.owner_id != request.member.pk:
        messages.error(request, "Only the goal's owner can edit it.")
        return redirect(goal.get_absolute_url())
    has_subgoals = goal.has_subgoals
    if request.method == "POST":
        form = GoalForm(request.POST, instance=goal, has_subgoals=has_subgoals)
        if form.is_valid():
            form.save()
            messages.success(request, "Goal updated.")
            return redirect(goal.get_absolute_url())
    else:
        form = GoalForm(instance=goal, has_subgoals=has_subgoals)
    return render(request, "tracker/goal_form.html", {
        "form": form, "goal": goal, "board": goal.board, "parent": goal.parent, "is_new": False,
    })


@require_member
def goal_delete(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    if goal.owner_id != request.member.pk:
        messages.error(request, "Only the goal's owner can delete it.")
        return redirect(goal.get_absolute_url())
    redirect_to = goal.parent.get_absolute_url() if goal.parent else goal.board.get_absolute_url()
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

    if scope == "board":
        base_qs = Goal.objects.filter(board_id=scope_id, parent__isnull=True)
    elif scope == "parent":
        base_qs = Goal.objects.filter(parent_id=scope_id)
    else:
        return HttpResponseBadRequest("Unknown scope")

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
                    gid = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if gid not in valid_ids:
                    continue
                goal = Goal.objects.get(pk=gid)
                if goal.status != status or goal.order != index:
                    goal.status = status
                    goal.order = index
                    goal.save()

    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Leaderboard / profiles
# ---------------------------------------------------------------------------

def leaderboard(request):
    return render(request, "tracker/leaderboard.html", {"members": member_leaderboard()})


def member_profile(request, slug):
    member = get_object_or_404(Member, slug=slug)
    top_level = list(member.goals.filter(parent__isnull=True).select_related("board"))
    return render(request, "tracker/member_profile.html", {"member": member, "goals": top_level})
