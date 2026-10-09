from django import forms
from django.utils import timezone

from apps.accounts.models import User
from .models import Project, ProjectDocument, ProjectStage, SupervisorDecision


class SupervisorAssignmentForm(forms.Form):
    supervisor = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Assign supervisor",
        empty_label="Choose a supervisor",
    )
    reason = forms.CharField(
        required=False,
        max_length=1000,
        label="Reason for assignment or change",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, supervisor_queryset, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supervisor"].queryset = supervisor_queryset


class UnassignedSuperviseeForm(forms.Form):
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        label="Student project to add",
        empty_label="Choose an unassigned student project",
    )
    reason = forms.CharField(required=False, max_length=1000, widget=forms.TextInput(attrs={"placeholder": "Optional note"}))

    def __init__(self, *args, project_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = project_queryset or Project.objects.none()


class SupervisorProjectEditForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ("title", "description", "keywords")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class ProjectProposalForm(forms.Form):
    proposed_title = forms.CharField(max_length=255, label="Project title")
    problem_statement = forms.CharField(widget=forms.Textarea)
    objectives = forms.CharField(widget=forms.Textarea)
    methodology = forms.CharField(widget=forms.Textarea)
    tools_and_technologies = forms.CharField(max_length=255, required=False)
    literature_review = forms.CharField(required=False, widget=forms.Textarea)
    research_gap = forms.CharField(required=False, widget=forms.Textarea)
    working_project_demonstration = forms.CharField(required=False, widget=forms.Textarea, label="Working project or demonstration evidence")
    student_name_on_form = forms.CharField(max_length=150, required=False)
    signed_on = forms.DateField(required=False, initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}))


class ProjectStartForm(forms.Form):
    title = forms.CharField(max_length=255, label="Working project title")
    description = forms.CharField(required=False, widget=forms.Textarea)
    keywords = forms.CharField(max_length=255, required=False, help_text="Comma-separated topic keywords")


class SupervisorDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=SupervisorDecision.choices)
    comments = forms.CharField(required=False, widget=forms.Textarea)
    name_on_form = forms.CharField(max_length=150)
    signed_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), initial=timezone.localdate)


class CoordinatorApprovalForm(forms.Form):
    notes = forms.CharField(required=False, widget=forms.Textarea)
    logged_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), initial=timezone.localdate)


class StageActionForm(forms.Form):
    note = forms.CharField(required=False, widget=forms.Textarea)
    when = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), initial=timezone.localdate)


class CompletionForm(forms.Form):
    signed_on = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), initial=timezone.localdate, label="Signed off on",
        help_text="The day the student brought the final documents and you signed them off.",
    )
    completion_note = forms.CharField(
        required=False, widget=forms.Textarea, label="Sign-off note",
        help_text="What you checked, e.g. bound copies and corrections received.",
    )
    gap_summary = forms.CharField(
        required=False,
        widget=forms.Textarea,
        help_text="The documented gap a future student could pick up.",
    )
    no_gap = forms.BooleanField(required=False, label="I confirm there is no documented gap to record")
    graduation_verified = forms.BooleanField(required=False)
    graduation_year = forms.IntegerField(required=False, min_value=1900, max_value=2200)

    def clean(self):
        # Same rule as sign_off_completion(); checked here too so the HOD sees it beside the fields.
        cleaned = super().clean()
        has_gap = bool((cleaned.get("gap_summary") or "").strip())
        if has_gap and cleaned.get("no_gap"):
            raise forms.ValidationError("Either record the gap or confirm there is none, not both.")
        if not has_gap and not cleaned.get("no_gap"):
            raise forms.ValidationError("Record the documented gap, or confirm that there is none.")
        return cleaned


class ProjectCsvImportForm(forms.Form):
    file = forms.FileField(help_text="CSV up to 10 MB; use the template headers shown below.")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > 10 * 1024 * 1024:
            raise forms.ValidationError("CSV files must be 10 MB or smaller.")
        if not upload.name.lower().endswith(".csv"):
            raise forms.ValidationError("Choose a .csv file.")
        return upload


class ProjectDocumentForm(forms.ModelForm):
    class Meta:
        model = ProjectDocument
        fields = ("title", "document_type", "file")
