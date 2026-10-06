import re

from bson import ObjectId
from django import forms
from django.forms.utils import flatatt
from django.utils.html import format_html, format_html_join

from .models import CATEGORY_PALETTE, Category, Decision, Event, EventComment, Goal, GoalBoard, Meeting, Member, TodoTask, GoalComment, TodoTaskComment


class AppLoginForm(forms.Form):
    password = forms.CharField(
        label="",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Password",
            "autofocus": True,
            "autocomplete": "current-password",
        }),
    )


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Your name", "autofocus": True}),
        }


class GoalBoardForm(forms.ModelForm):
    class Meta:
        model = GoalBoard
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. 2026 Goals"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class CategoryForm(forms.ModelForm):
    color = forms.ChoiceField(choices=CATEGORY_PALETTE, widget=forms.RadioSelect)

    class Meta:
        model = Category
        fields = ["name", "color"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Travel, Home, Side Project"}),
        }


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = [
            "title", "description", "category",
            "start_date", "end_date", "status", "progress_percent", "assignees",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "progress_percent": forms.NumberInput(attrs={"min": 0, "max": 100, "step": 5}),
        }
        labels = {
            "start_date": "Start date (optional)",
            "end_date": "End date (optional)",
        }

    def __init__(self, *args, board=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(board=board) if board else Category.objects.none()
        self.fields["category"].required = False
        self.fields["assignees"].queryset = Member.objects.all()
        self.fields["assignees"].widget = forms.SelectMultiple(attrs={"size": 4})

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end <= start:
            self.add_error("end_date", "End date must be after the start date.")
        return cleaned


class BoardFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Keyword")
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=False)
    owner = forms.ModelChoiceField(queryset=Member.objects.all(), required=False)
    start_after = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end_before = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, goals_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if goals_queryset is not None:
            self.fields["category"].queryset = Category.objects.filter(
                goals__in=goals_queryset
            ).distinct()
            self.fields["owner"].queryset = Member.objects.filter(
                goals__in=goals_queryset
            ).distinct()


class TodoTaskForm(forms.ModelForm):
    class Meta:
        model = TodoTask
        fields = ["title", "due_date", "assignees"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Add a task"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "due_date": "Deadline",
            "assignees": "Assign to",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignees"].queryset = Member.objects.all()
        self.fields["assignees"].widget = forms.CheckboxSelectMultiple()


class GoalImportForm(forms.Form):
    file = forms.FileField(label="Goals JSON file")


class DeleteConfirmationForm(forms.Form):
    name = forms.CharField(label="Type the item name to confirm")


class GoalCommentForm(forms.ModelForm):
    class Meta:
        model = GoalComment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 2, "placeholder": "Add a comment"}),
        }


class TodoTaskCommentForm(forms.ModelForm):
    class Meta:
        model = TodoTaskComment
        fields = ["text"]
        widgets = {
            "text": forms.TextInput(attrs={"placeholder": "Add a comment"}),
        }


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "description", "date", "participants"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "date": forms.DateInput(attrs={"type": "date"}),
            "participants": forms.SelectMultiple(attrs={"size": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["participants"].queryset = Member.objects.all()


class EventFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Keyword")
    participant = forms.ModelChoiceField(queryset=Member.objects.all(), required=False)
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    include_past = forms.BooleanField(required=False, label="Include past events")


class EventCommentForm(forms.ModelForm):
    class Meta:
        model = EventComment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 2, "placeholder": "Add a comment"}),
        }


class MeetingForm(forms.ModelForm):
    when = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    class Meta:
        model = Meeting
        fields = ["title", "when", "notes", "participants"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Agenda, notes, decisions..."}),
            "participants": forms.SelectMultiple(attrs={"size": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["participants"].queryset = Member.objects.all()


class MeetingFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Keyword")
    participant = forms.ModelChoiceField(queryset=Member.objects.all(), required=False)
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="From")
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="To")
    upcoming_only = forms.BooleanField(required=False, label="Upcoming only")


def _decision_label(decision):
    return f"{decision.title} [{decision.pk}]"


class ParentRefsWidget(forms.Widget):
    """One text box per parent (each backed by the shared <datalist> of
    "Title [id]" suggestions) plus a blank one for adding another. Submits
    every box under the same name; with JS, a button adds more boxes."""

    def value_from_datadict(self, data, files, name):
        return data.getlist(name) if hasattr(data, "getlist") else data.get(name, [])

    def value_omitted_from_data(self, data, files, name):
        return name not in data

    def render(self, name, value, attrs=None, renderer=None):
        values = [v for v in (value or []) if v] + [""]
        attrs = self.build_attrs(self.attrs, attrs)
        base_id = attrs.pop("id", f"id_{name}")
        inputs = format_html_join(
            "",
            '<input type="text" name="{}" value="{}" id="{}"{}>',
            (
                (name, v, base_id if i == 0 else f"{base_id}_{i}", flatatt(attrs))
                for i, v in enumerate(values)
            ),
        )
        return format_html(
            '<span class="parent-refs" data-parent-refs>{}</span>'
            '<button type="button" class="btn" data-add-parent hidden>Add another parent</button>',
            inputs,
        )


class ParentRefsField(forms.Field):
    widget = ParentRefsWidget

    def to_python(self, value):
        if isinstance(value, str):
            value = [value]
        return [v.strip() for v in (value or []) if v and v.strip()]


class DecisionForm(forms.ModelForm):
    # Typed free text so a parent can be found by searching either its title
    # or its id. Any number of parents can be given.
    parent_refs = ParentRefsField(
        required=False,
        label="Parent decisions",
        help_text="Search by title or id. Add several if this decision follows from more than one. Leave blank for a top-level decision.",
        widget=ParentRefsWidget(attrs={"list": "decision-options", "autocomplete": "off", "placeholder": "Title or id"}),
    )

    class Meta:
        model = Decision
        fields = ["title", "status", "description", "start_date", "end_date", "motivation", "rollback_reasons"]
        labels = {"rollback_reasons": "Reasons to discontinue or roll back"}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "motivation": forms.Textarea(attrs={"rows": 3, "placeholder": "Why was this decision made?"}),
            "rollback_reasons": forms.Textarea(attrs={"rows": 3, "placeholder": "What would make us stop or reverse this?"}),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    field_order = ["title", "status", "parent_refs", "description", "start_date", "end_date", "motivation", "rollback_reasons"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        excluded = set()
        if self.instance.pk:
            excluded = {self.instance.pk} | self.instance.descendant_ids()
            if not self.is_bound:
                self.initial["parent_refs"] = [_decision_label(p) for p in self.instance.parents.order_by("start_date", "title")]
        self.parent_choices = Decision.objects.exclude(pk__in=excluded).order_by("title")

    def _resolve_parent(self, ref):
        # Accept "Title [id]" (from the suggestions), a bare id, or a title.
        match = re.search(r"\[([0-9a-fA-F]{24})\]\s*$", ref)
        candidate_id = match.group(1) if match else ref
        if ObjectId.is_valid(candidate_id):
            found = self.parent_choices.filter(pk=ObjectId(candidate_id)).first()
            if found:
                return found
        matches = list(self.parent_choices.filter(title__iexact=ref)[:2])
        if not matches:
            matches = list(self.parent_choices.filter(title__icontains=ref)[:2])
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise forms.ValidationError(f"Several decisions match “{ref}” — pick one from the suggestions or use its id.")
        raise forms.ValidationError(f"No decision matches “{ref}” (a decision can't be its own ancestor).")

    def clean_parent_refs(self):
        parents, errors = [], []
        for ref in self.cleaned_data["parent_refs"]:
            try:
                parent = self._resolve_parent(ref)
            except forms.ValidationError as exc:
                errors.extend(exc.messages)
                continue
            if parent not in parents:
                parents.append(parent)
        if errors:
            raise forms.ValidationError(errors)
        return parents

    def _save_m2m(self):
        super()._save_m2m()
        self.instance.parents.set(self.cleaned_data["parent_refs"])


class DecisionFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Keyword or id")
    status = forms.ChoiceField(choices=[("", "Any")] + Decision.STATUS_CHOICES, required=False)
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="From")
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="To")
