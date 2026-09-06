from django import forms

from .models import CATEGORY_PALETTE, Category, Goal, GoalBoard, Member, TodoTask


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
        self.fields["assignees"].widget = forms.SelectMultiple(attrs={"size": 4})


class GoalImportForm(forms.Form):
    file = forms.FileField(label="Goals JSON file")


class DeleteConfirmationForm(forms.Form):
    name = forms.CharField(label="Type the item name to confirm")
