from django import forms

from .models import Goal, GoalBoard, Member


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


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = [
            "title", "description", "category",
            "start_date", "end_date", "status", "progress_percent",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "category": forms.TextInput(attrs={"placeholder": "e.g. Financial, Health, Career"}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "progress_percent": forms.NumberInput(attrs={"min": 0, "max": 100, "step": 5}),
        }

    def __init__(self, *args, has_subgoals=False, **kwargs):
        super().__init__(*args, **kwargs)
        if has_subgoals:
            # Progress is derived from subgoals once a goal has any.
            self.fields.pop("progress_percent")

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end <= start:
            self.add_error("end_date", "End date must be after the start date.")
        return cleaned
