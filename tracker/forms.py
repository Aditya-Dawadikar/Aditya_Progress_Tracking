import json

from django import forms

from .models import (
    GeneratedTestCase,
    Pattern,
    Problem,
    ProblemAttempt,
    SubmissionFailure,
    Test,
)


class ProblemForm(forms.ModelForm):
    class Meta:
        model = Problem
        fields = [
            "leetcode_number",
            "title",
            "leetcode_url",
            "difficulty",
            "primary_pattern",
            "secondary_patterns",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "secondary_patterns": forms.SelectMultiple(attrs={"size": 6}),
        }


class TestForm(forms.ModelForm):
    class Meta:
        model = Test
        fields = ["name", "date", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class TestPlanImportForm(forms.Form):
    json_file = forms.FileField(label="Test Plan JSON")

    def clean_json_file(self):
        f = self.cleaned_data["json_file"]
        raw = f.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise forms.ValidationError("File is not valid UTF-8 text.") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"File is not valid JSON: {exc}") from exc
        return data


class NoveltyForm(forms.Form):
    novelty = forms.ChoiceField(choices=ProblemAttempt._meta.get_field("novelty").choices)


class PatternIdentifiedForm(forms.Form):
    predicted_primary_pattern = forms.ModelChoiceField(
        queryset=Pattern.objects.all(), required=False, label="What's the primary pattern?"
    )
    predicted_secondary_patterns = forms.ModelMultipleChoiceField(
        queryset=Pattern.objects.all(), required=False, label="Secondary pattern(s)?"
    )


class SubmitForm(forms.Form):
    result = forms.ChoiceField(choices=[
        ("accepted", "Accepted"),
        (SubmissionFailure.RESULT_WRONG_ANSWER, "Wrong Answer"),
        (SubmissionFailure.RESULT_TLE, "TLE"),
        (SubmissionFailure.RESULT_MLE, "MLE"),
        (SubmissionFailure.RESULT_RUNTIME_ERROR, "Runtime Error"),
        (SubmissionFailure.RESULT_OTHER, "Other"),
    ])
    confidence = forms.ChoiceField(
        choices=[("", "—")] + list(ProblemAttempt.CONFIDENCE_CHOICES), required=False
    )


class FailureAnalysisForm(forms.ModelForm):
    class Meta:
        model = SubmissionFailure
        fields = ["failure_type", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class AbandonForm(forms.Form):
    confidence = forms.ChoiceField(
        choices=[("", "—")] + list(ProblemAttempt.CONFIDENCE_CHOICES), required=False
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)


class TestCaseForm(forms.ModelForm):
    class Meta:
        model = GeneratedTestCase
        fields = ["category", "description", "expected_behavior", "did_find_bug", "notes"]
        widgets = {
            "description": forms.TextInput(),
            "expected_behavior": forms.TextInput(),
            "notes": forms.Textarea(attrs={"rows": 1}),
        }


class PatternReviewForm(forms.ModelForm):
    class Meta:
        model = ProblemAttempt
        fields = ["pattern_identification_result"]
