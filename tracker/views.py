import hmac
import json
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .auth import issue_token
from .forms import AppLoginForm, BoardFilterForm, CategoryForm, DeleteConfirmationForm, EventCommentForm, EventFilterForm, EventForm, GoalBoardForm, GoalCommentForm, GoalForm, GoalImportForm, MeetingFilterForm, MeetingForm, MemberForm, TodoTaskCommentForm, TodoTaskForm
from .models import Category, Event, EventComment, Goal, GoalActivity, GoalBoard, GoalComment, Meeting, Member, TodoTask, TodoTaskComment
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


def record_activity(goal, actor, action, detail="", task=None):
    GoalActivity.objects.create(goal=goal, actor=actor, action=action, detail=detail, task=task)


# ---------------------------------------------------------------------------
# App-wide login (shared password -> JWT cookie). See tracker/auth.py and
# AppPasswordMiddleware. Separate from whoami/whoami_logout below, which is
# the password-less per-Member identity picker used once inside the app.
# ---------------------------------------------------------------------------

def app_login(request):
    next_url = safe_next_url(request, request.GET.get("next") or request.POST.get("next"))
    form = AppLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        entered = form.cleaned_data["password"].encode()
        expected = settings.APP_PASSWORD.encode()
        if hmac.compare_digest(entered, expected):
            response = redirect(next_url)
            response.set_cookie(
                settings.JWT_COOKIE_NAME,
                issue_token(),
                max_age=settings.JWT_MAX_AGE_SECONDS,
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
            )
            return response
        form.add_error("password", "Incorrect password.")

    return render(request, "tracker/login.html", {"form": form, "next": next_url})


def app_logout(request):
    response = redirect(reverse("tracker:login"))
    response.delete_cookie(settings.JWT_COOKIE_NAME)
    return response


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
# Events
# ---------------------------------------------------------------------------

def events_list(request):
    events = Event.objects.all()
    filter_form = EventFilterForm(request.GET or None)
    if filter_form.is_valid():
        data = filter_form.cleaned_data
        if not data["include_past"]:
            events = events.filter(date__gte=timezone.localdate())
        if data["q"]:
            events = events.filter(Q(title__icontains=data["q"]) | Q(description__icontains=data["q"]))
        if data["participant"]:
            events = events.filter(participants=data["participant"])
        if data["start_date"]:
            events = events.filter(date__gte=data["start_date"])
        if data["end_date"]:
            events = events.filter(date__lte=data["end_date"])
    return render(request, "tracker/events_list.html", {"events": events, "filter_form": filter_form})


@require_member
def event_create(request):
    if request.method == "POST":
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.member
            event.save()
            form.save_m2m()
            messages.success(request, f"Event “{event.title}” created.")
            return redirect(event.get_absolute_url())
    else:
        form = EventForm()
    return render(request, "tracker/event_form.html", {"form": form, "is_new": True})


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    return render(request, "tracker/event_detail.html", {"event": event, "comment_form": EventCommentForm()})


@require_member
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.created_by_id != request.member.pk:
        messages.error(request, "Only the event's creator can edit it.")
        return redirect(event.get_absolute_url())
    if request.method == "POST":
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "Event updated.")
            return redirect(event.get_absolute_url())
    else:
        form = EventForm(instance=event)
    return render(request, "tracker/event_form.html", {"form": form, "event": event, "is_new": False})


@require_member
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.created_by_id != request.member.pk:
        messages.error(request, "Only the event's creator can delete it.")
        return redirect(event.get_absolute_url())
    if request.method == "POST":
        form = DeleteConfirmationForm(request.POST)
        if form.is_valid() and form.cleaned_data["name"] == event.title:
            event.delete()
            messages.success(request, "Event deleted.")
            return redirect("tracker:events_list")
        form.add_error("name", "The name does not match this event.")
    else:
        form = DeleteConfirmationForm()
    return render(request, "tracker/event_confirm_delete.html", {"event": event, "form": form})


@require_member
@require_POST
def event_comment_create(request, pk):
    event = get_object_or_404(Event, pk=pk)
    form = EventCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.event = event
        comment.author = request.member
        comment.save()
        messages.success(request, "Comment added.")
    return redirect(event.get_absolute_url())


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------

def meetings_list(request):
    meetings = Meeting.objects.all()
    filter_form = MeetingFilterForm(request.GET)
    if filter_form.is_valid():
        data = filter_form.cleaned_data
        if data["upcoming_only"]:
            meetings = meetings.filter(when__gte=timezone.now())
        if data["q"]:
            meetings = meetings.filter(Q(title__icontains=data["q"]) | Q(notes__icontains=data["q"]))
        if data["participant"]:
            meetings = meetings.filter(participants=data["participant"])
        if data["start"]:
            start_dt = timezone.make_aware(datetime.combine(data["start"], datetime.min.time()))
            meetings = meetings.filter(when__gte=start_dt)
        if data["end"]:
            end_dt = timezone.make_aware(datetime.combine(data["end"], datetime.max.time()))
            meetings = meetings.filter(when__lte=end_dt)
    return render(request, "tracker/meetings_list.html", {"meetings": meetings, "filter_form": filter_form})


@require_member
def meeting_create(request):
    if request.method == "POST":
        form = MeetingForm(request.POST)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.created_by = request.member
            meeting.save()
            form.save_m2m()
            messages.success(request, f"Meeting “{meeting.title}” scheduled.")
            return redirect(meeting.get_absolute_url())
    else:
        form = MeetingForm()
    return render(request, "tracker/meeting_form.html", {"form": form, "is_new": True})


def meeting_detail(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    return render(request, "tracker/meeting_detail.html", {"meeting": meeting})


@require_member
def meeting_edit(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if meeting.created_by_id != request.member.pk:
        messages.error(request, "Only the meeting's creator can edit it.")
        return redirect(meeting.get_absolute_url())
    if request.method == "POST":
        form = MeetingForm(request.POST, instance=meeting)
        if form.is_valid():
            form.save()
            messages.success(request, "Meeting updated.")
            return redirect(meeting.get_absolute_url())
    else:
        form = MeetingForm(instance=meeting)
    return render(request, "tracker/meeting_form.html", {"form": form, "meeting": meeting, "is_new": False})


@require_member
def meeting_delete(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if meeting.created_by_id != request.member.pk:
        messages.error(request, "Only the meeting's creator can delete it.")
        return redirect(meeting.get_absolute_url())
    if request.method == "POST":
        form = DeleteConfirmationForm(request.POST)
        if form.is_valid() and form.cleaned_data["name"] == meeting.title:
            meeting.delete()
            messages.success(request, "Meeting deleted.")
            return redirect("tracker:meetings_list")
        form.add_error("name", "The name does not match this meeting.")
    else:
        form = DeleteConfirmationForm()
    return render(request, "tracker/meeting_confirm_delete.html", {"meeting": meeting, "form": form})


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@require_member
def category_list(request, pk):
    board = get_object_or_404(GoalBoard, pk=pk)
    if board.created_by_id != request.member.pk:
        messages.error(request, "Only the board's creator can manage its categories.")
        return redirect(board.get_absolute_url())
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.board = board
            category.created_by = request.member
            category.save()
            messages.success(request, f"Category “{category.name}” created.")
            return redirect("tracker:category_list", pk=board.pk)
    else:
        form = CategoryForm()
    return render(request, "tracker/categories.html", {
        "board": board,
        "form": form,
        "categories": board.categories.all(),
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
def board_settings(request, pk):
    board = get_object_or_404(GoalBoard, pk=pk)
    if board.created_by_id != request.member.pk:
        messages.error(request, "Only the board's creator can open its settings.")
        return redirect(board.get_absolute_url())
    return render(request, "tracker/board_settings.html", {"board": board})


@require_member
def board_delete(request, pk):
    board = get_object_or_404(GoalBoard, pk=pk)
    if board.created_by_id != request.member.pk:
        messages.error(request, "Only the board's creator can delete it.")
        return redirect(board.get_absolute_url())
    if request.method == "POST":
        form = DeleteConfirmationForm(request.POST)
        if form.is_valid() and form.cleaned_data["name"] == board.name:
            board.delete()
            messages.success(request, f"Board “{board.name}” deleted.")
            return redirect("tracker:boards_list")
        form.add_error("name", "The name does not match this board.")
    else:
        form = DeleteConfirmationForm()
    return render(request, "tracker/board_confirm_delete.html", {"board": board, "form": form})


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
        form = GoalForm(request.POST, board=board)
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
                form.save_m2m()
                record_activity(goal, request.member, "goal_created", "Created this goal.")
                if goal.assignees.exists():
                    record_activity(goal, request.member, "goal_assignees_updated", "Assigned: " + ", ".join(goal.assignees.values_list("name", flat=True)))
                messages.success(request, f"Goal “{goal.title}” created.")
                return redirect(board.get_absolute_url())
    else:
        form = GoalForm(board=board)

    return render(request, "tracker/goal_form.html", {
        "form": form, "board": board, "is_new": True,
    })


def goal_detail(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    return render(request, "tracker/goal_detail.html", {
        "goal": goal,
        "task_form": TodoTaskForm(),
        "goal_comment_form": GoalCommentForm(),
        "task_comment_form": TodoTaskCommentForm(),
    })


@require_member
def goal_edit(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    if goal.owner_id != request.member.pk:
        messages.error(request, "Only the goal's owner can edit it.")
        return redirect(goal.get_absolute_url())
    if request.method == "POST":
        form = GoalForm(request.POST, instance=goal, board=goal.board)
        if form.is_valid():
            changed_fields = form.changed_data
            form.save()
            if "assignees" in changed_fields:
                names = ", ".join(goal.assignees.values_list("name", flat=True)) or "Unassigned"
                record_activity(goal, request.member, "goal_assignees_updated", f"Assigned: {names}")
            other_changes = [field.replace("_", " ") for field in changed_fields if field != "assignees"]
            if other_changes:
                record_activity(goal, request.member, "goal_updated", "Updated: " + ", ".join(other_changes))
            messages.success(request, "Goal updated.")
            return redirect(goal.get_absolute_url())
    else:
        form = GoalForm(instance=goal, board=goal.board)
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
        form = DeleteConfirmationForm(request.POST)
        if form.is_valid() and form.cleaned_data["name"] == goal.title:
            title = goal.title
            goal.delete()
            messages.success(request, f"Goal “{title}” deleted.")
            return redirect(redirect_to)
        form.add_error("name", "The name does not match this goal.")
    else:
        form = DeleteConfirmationForm()
    return render(request, "tracker/goal_confirm_delete.html", {"goal": goal, "form": form})


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
                    previous_status = goal.status
                    goal.status = status
                    goal.order = index
                    goal.save()
                    if previous_status != status:
                        record_activity(goal, request.member, "goal_status_changed", f"Status changed to {valid_statuses[status]}.")

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
        form.save_m2m()
        record_activity(goal, request.member, "task_created", f"Added task: {task.title}", task=task)
        if task.assignees.exists():
            record_activity(goal, request.member, "task_assignees_updated", "Assigned: " + ", ".join(task.assignees.values_list("name", flat=True)), task=task)
        messages.success(request, "Task added.")
    return redirect(goal.get_absolute_url())


@require_member
@require_POST
def task_toggle(request, pk):
    task = get_object_or_404(TodoTask, pk=pk)
    if task.goal.owner_id == request.member.pk:
        task.completed = not task.completed
        task.save(update_fields=["completed"])
        record_activity(task.goal, request.member, "task_completed" if task.completed else "task_reopened", task=task, detail=task.title)
    return redirect(task.goal.get_absolute_url())


@require_member
def task_delete(request, pk):
    task = get_object_or_404(TodoTask, pk=pk)
    goal = task.goal
    if goal.owner_id != request.member.pk:
        return redirect(goal.get_absolute_url())
    if request.method == "POST":
        form = DeleteConfirmationForm(request.POST)
        if form.is_valid() and form.cleaned_data["name"] == task.title:
            record_activity(goal, request.member, "task_deleted", f"Deleted task: {task.title}")
            task.delete()
            messages.success(request, "Task deleted.")
            return redirect(goal.get_absolute_url())
        form.add_error("name", "The name does not match this task.")
    else:
        form = DeleteConfirmationForm()
    return render(request, "tracker/task_confirm_delete.html", {"task": task, "goal": goal, "form": form})


@require_member
@require_POST
def goal_comment_create(request, pk):
    goal = get_object_or_404(Goal, pk=pk)
    form = GoalCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.goal = goal
        comment.author = request.member
        comment.save()
        record_activity(goal, request.member, "goal_commented", "Added a comment.")
    return redirect(goal.get_absolute_url())


@require_member
@require_POST
def task_comment_create(request, pk):
    task = get_object_or_404(TodoTask, pk=pk)
    form = TodoTaskCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.member
        comment.save()
        record_activity(task.goal, request.member, "task_commented", "Added a comment.", task=task)
    return redirect(task.goal.get_absolute_url())


# ---------------------------------------------------------------------------
# Leaderboard / profiles
# ---------------------------------------------------------------------------

def leaderboard(request):
    return render(request, "tracker/leaderboard.html", {"members": member_leaderboard()})


def member_profile(request, slug):
    member = get_object_or_404(Member, slug=slug)
    top_level = list(member.goals.select_related("board", "category"))
    return render(request, "tracker/member_profile.html", {"member": member, "goals": top_level})
