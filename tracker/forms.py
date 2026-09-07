from django import forms

from .models import CATEGORY_PALETTE, Category, Event, EventComment, Goal, GoalBoard, Meeting, Member, TodoTask, GoalComment, TodoTaskComment


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
    include_past = forms.BooleanField(required=False, label="Include past meetings")
