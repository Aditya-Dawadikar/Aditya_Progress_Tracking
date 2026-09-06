from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


def _clamp(value, low, high):
    return max(low, min(high, value))


class Member(models.Model):
    """A lightweight, password-less identity chosen via the /whoami/ picker."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("tracker:member_profile", args=[self.slug])


class GoalBoard(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="boards_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("tracker:board_detail", args=[self.pk])

    @property
    def top_level_goals(self):
        return self.goals.filter(parent__isnull=True)


class Goal(models.Model):
    STATUS_NOT_STARTED = "not_started"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_ABANDONED = "abandoned"
    STATUS_CHOICES = [
        (STATUS_NOT_STARTED, "Not Started"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_ABANDONED, "Abandoned"),
    ]
    STATUS_ORDER = [STATUS_NOT_STARTED, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_ABANDONED]

    board = models.ForeignKey(GoalBoard, on_delete=models.CASCADE, related_name="goals")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="subgoals"
    )
    owner = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="goals")

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOT_STARTED)
    start_date = models.DateField()
    end_date = models.DateField()

    progress_percent = models.PositiveSmallIntegerField(default=0)
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("tracker:goal_detail", args=[self.pk])

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError("End date must be after the start date.")
        if self.parent_id:
            parent = self.parent
            if self.start_date and parent.start_date and self.start_date < parent.start_date:
                raise ValidationError("A subgoal can't start before its parent goal.")
            if self.end_date and parent.end_date and self.end_date > parent.end_date:
                raise ValidationError("A subgoal can't end after its parent goal.")

    def save(self, *args, **kwargs):
        if self.parent_id:
            self.board_id = self.parent.board_id
        was_completed = False
        if self.pk:
            was_completed = Goal.objects.filter(pk=self.pk).values_list("status", flat=True).first() == self.STATUS_COMPLETED
        if self.status == self.STATUS_COMPLETED:
            self.progress_percent = 100
            if not self.completed_at:
                self.completed_at = timezone.now()
        elif was_completed and self.status != self.STATUS_COMPLETED:
            self.completed_at = None
        super().save(*args, **kwargs)

    @property
    def has_subgoals(self):
        return self.subgoals.exists()

    @property
    def effective_progress(self):
        """Own progress_percent for leaf goals; average of subgoals otherwise."""
        children = list(self.subgoals.all())
        if not children:
            return self.progress_percent
        return round(sum(c.effective_progress for c in children) / len(children))

    @property
    def time_fraction(self):
        """0..1 fraction of the goal's window that has elapsed."""
        total_days = (self.end_date - self.start_date).days
        if total_days <= 0:
            return 1.0
        elapsed_days = (timezone.localdate() - self.start_date).days
        return _clamp(elapsed_days / total_days, 0.0, 1.0)

    @property
    def time_fraction_percent(self):
        return round(self.time_fraction * 100)

    @property
    def pace_score(self):
        """0..100 normalized on-pace score. 50 = exactly on schedule."""
        progress_fraction = self.effective_progress / 100
        return round(_clamp(50 + 50 * (progress_fraction - self.time_fraction), 0, 100))

    @property
    def is_overdue(self):
        return self.status not in (self.STATUS_COMPLETED, self.STATUS_ABANDONED) and timezone.localdate() > self.end_date

    def reorder_siblings_queryset(self):
        qs = Goal.objects.filter(parent=self.parent)
        if self.parent_id is None:
            qs = qs.filter(board=self.board)
        return qs
