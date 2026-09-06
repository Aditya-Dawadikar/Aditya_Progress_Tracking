from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django_mongodb_backend.fields import ObjectIdAutoField

# A small, fixed set of swatches offered when creating a category — keeps the
# palette visually consistent instead of a full color wheel.
CATEGORY_PALETTE = [
    ("#4F7A62", "Sage"),
    ("#E6A65D", "Amber"),
    ("#7B6DCC", "Periwinkle"),
    ("#5C8FC7", "Sky"),
    ("#C1584A", "Terracotta"),
    ("#4FA39A", "Teal"),
    ("#C77DAE", "Orchid"),
    ("#8A8578", "Stone"),
]
DEFAULT_CATEGORY_COLOR = CATEGORY_PALETTE[0][0]


def _clamp(value, low, high):
    return max(low, min(high, value))


class Member(models.Model):
    """A lightweight, password-less identity chosen via the /whoami/ picker."""

    id = ObjectIdAutoField(primary_key=True)
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


class Category(models.Model):
    id = ObjectIdAutoField(primary_key=True)
    board = models.ForeignKey("GoalBoard", on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default=DEFAULT_CATEGORY_COLOR)
    created_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="categories_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(fields=["board", "name"], name="unique_category_name_per_board"),
        ]

    def __str__(self):
        return self.name


class GoalBoard(models.Model):
    id = ObjectIdAutoField(primary_key=True)
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
        return self.goals.all()


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

    id = ObjectIdAutoField(primary_key=True)
    board = models.ForeignKey(GoalBoard, on_delete=models.CASCADE, related_name="goals")
    owner = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="goals")
    assignees = models.ManyToManyField(Member, blank=True, related_name="assigned_goals")

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="goals"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOT_STARTED)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

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
    def save(self, *args, **kwargs):
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
    def has_tasks(self):
        return self.tasks.exists()

    @property
    def effective_progress(self):
        """Own progress_percent unless tasks exist, then task completion percentage."""
        tasks = list(self.tasks.all())
        if not tasks:
            return self.progress_percent
        return round(sum(task.completed for task in tasks) * 100 / len(tasks))

    @property
    def time_fraction(self):
        """0..1 fraction of the goal's window that has elapsed, or None with no deadline."""
        if not self.start_date or not self.end_date:
            return None
        total_days = (self.end_date - self.start_date).days
        if total_days <= 0:
            return 1.0
        elapsed_days = (timezone.localdate() - self.start_date).days
        return _clamp(elapsed_days / total_days, 0.0, 1.0)

    @property
    def time_fraction_percent(self):
        fraction = self.time_fraction
        return round(fraction * 100) if fraction is not None else None

    @property
    def pace_score(self):
        """0..100 normalized on-pace score, or None with no deadline. 50 = on schedule."""
        fraction = self.time_fraction
        if fraction is None:
            return None
        progress_fraction = self.effective_progress / 100
        return round(_clamp(50 + 50 * (progress_fraction - fraction), 0, 100))

    @property
    def is_overdue(self):
        if not self.end_date:
            return False
        return self.status not in (self.STATUS_COMPLETED, self.STATUS_ABANDONED) and timezone.localdate() > self.end_date


class TodoTask(models.Model):
    """A single, non-nestable checklist item belonging to one goal."""

    id = ObjectIdAutoField(primary_key=True)
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="tasks")
    assignees = models.ManyToManyField(Member, blank=True, related_name="assigned_tasks")
    title = models.CharField(max_length=200)
    completed = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return not self.completed and self.due_date is not None and self.due_date < timezone.localdate()

    @property
    def deadline_label(self):
        if not self.due_date:
            return None
        days_remaining = (self.due_date - timezone.localdate()).days
        if self.completed:
            return f"Due {self.due_date:%b} {self.due_date.day}"
        if days_remaining < 0:
            return f"Overdue by {-days_remaining} day{'s' if days_remaining != -1 else ''}"
        if days_remaining == 0:
            return "Due today"
        return f"{days_remaining} day{'s' if days_remaining != 1 else ''} left"
