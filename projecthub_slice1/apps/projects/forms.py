from django import forms
from django.utils import timezone

from apps.academics.models import SEMESTER_CODE, normalise_semester_code
from apps.accounts.models import User
from .models import Project, ProjectDocument, ProjectMedia, ProjectStage, SupervisorDecision
from .models.media import (
    MAXIMUM_IMAGE_BYTES, MAXIMUM_IMAGES_PER_PROJECT, MAXIMUM_VIDEO_BYTES, MAXIMUM_VIDEOS_PER_PROJECT,
    validate_media_upload, validate_video_link,
)


class SupervisorChoiceField(forms.ModelChoiceField):
    """Shows each supervisor's current load, e.g. "Dr Julius Makinde (3 active)", to keep numbers even."""

    def label_from_instance(self, obj):
        name = obj.get_full_name() or obj.username
        count = getattr(obj, "active_project_count", None)
        return name if count is None else f"{name} ({count} active)"


class SupervisorAssignmentForm(forms.Form):
    supervisor = SupervisorChoiceField(
        queryset=User.objects.none(),
        label="Assign supervisor",
        empty_label="Choose a supervisor",
    )
    reason = forms.CharField(
        required=False,
        max_length=1000,
        label="Reason for assignment or change",
        help_text="Required when changing a supervisor, e.g. \"Student asked: wants a supervisor in AI\".",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, supervisor_queryset, current_supervisor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_supervisor = current_supervisor
        self.fields["supervisor"].queryset = supervisor_queryset

    def clean(self):
        cleaned = super().clean()
        supervisor = cleaned.get("supervisor")
        changing = self.current_supervisor is not None and supervisor is not None and supervisor != self.current_supervisor
        if changing and not cleaned.get("reason", "").strip():
            self.add_error("reason", "Say why the supervisor is changing; it is kept in the history.")
        return cleaned


class SemesterCodeField(forms.CharField):
    """A semester typed by hand, like 26A (D-38). Cleans to the code in one form ("26 a" -> "26A"),
    or "" when left empty. Codes already in use are offered as suggestions (the semester_codes tag)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("max_length", 20)  # room for a mistyped value, so the format message explains it
        kwargs.setdefault("label", "Semester")
        kwargs.setdefault("widget", forms.TextInput(attrs={
            "placeholder": "26A", "list": "semester-codes", "autocomplete": "off", "autocapitalize": "characters",
            "size": 6, "class": "semester-input",
        }))
        super().__init__(**kwargs)

    def clean(self, value):
        code = normalise_semester_code(super().clean(value))
        if code and not SEMESTER_CODE.match(code):
            raise forms.ValidationError("Type the semester as two digits and A, B or C, like 26A.")
        return code


def semester_field(help_text=""):
    return SemesterCodeField(help_text=help_text)


class AllocationForm(SupervisorAssignmentForm):
    """Allocating a supervisor to a student who has no project yet: the semester can be chosen too."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["semester"] = semester_field("The project's semester, like 26A. Optional; you can set it later.")


class ProjectSemesterForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["semester"] = semester_field("Type it, like 26A. A new semester is added the first time it is used; leave empty for not set.")


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


# Keywords are optional tags that only help search; the label and example say so in a few words.
KEYWORDS_LABEL = "Keywords (optional)"
KEYWORDS_HELP = "A few words about the topic, separated by commas. They help people find the project in a search."
KEYWORDS_PLACEHOLDER = "e.g. fintech, fraud detection, mobile money"


class SupervisorProjectEditForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ("title", "description", "keywords")
        labels = {"keywords": KEYWORDS_LABEL}
        help_texts = {"keywords": KEYWORDS_HELP}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "keywords": forms.TextInput(attrs={"placeholder": KEYWORDS_PLACEHOLDER}),
        }


class ProjectProposalForm(forms.Form):
    """The student's proposal. Only the fields their supervisor's approval method needs are shown,
    and a draft needs only the title; submitting needs every shown field except the tools."""

    proposed_title = forms.CharField(max_length=255, label="Project title")
    problem_statement = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), label="Problem statement",
                                        help_text="The problem your project solves, and for whom.")
    objectives = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), label="Objectives",
                                 help_text="What the project will achieve, as a short list.")
    methodology = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), label="Methodology",
                                  help_text="How you will do it: research method, design and development approach.")
    tools_and_technologies = forms.CharField(max_length=255, required=False, label="Tools and technologies (optional)",
                                             help_text="For example Python, Django, MySQL.")
    literature_review = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}), label="Literature review",
                                        help_text="Your supervisor asks for this before deciding.")
    research_gap = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Research gap",
                                   help_text="What existing work does not cover, which your project will.")
    working_project_demonstration = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}),
                                                    label="Working project or demonstration evidence",
                                                    help_text="Your supervisor asks for this before deciding, e.g. a prototype link.")

    def __init__(self, *args, method="topic_only", draft=False, **kwargs):
        super().__init__(*args, **kwargs)
        if method != "literature_review":
            del self.fields["literature_review"], self.fields["research_gap"]
        if method != "working_project":
            del self.fields["working_project_demonstration"]
        if draft:
            for name, field in self.fields.items():
                field.required = name == "proposed_title"


class ProjectStartForm(forms.Form):
    title = forms.CharField(max_length=255, label="Working project title")
    description = forms.CharField(required=False, widget=forms.Textarea)
    keywords = forms.CharField(
        max_length=255, required=False, label=KEYWORDS_LABEL, help_text=KEYWORDS_HELP,
        widget=forms.TextInput(attrs={"placeholder": KEYWORDS_PLACEHOLDER}),
    )


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
        if cleaned.get("graduation_verified") and not cleaned.get("graduation_year"):
            self.add_error("graduation_year", "Enter the graduation year when you tick Graduation verified.")
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


class ProjectMediaForm(forms.Form):
    """Add a screenshot or a demo video (an upload or a link) to a running or archived project (D-30)."""

    kind = forms.ChoiceField(choices=ProjectMedia.Kind.choices, label="Type")
    caption = forms.CharField(max_length=180, label="Short description", help_text="For example \"Login screen\" or \"Full demo\".")
    file = forms.FileField(
        required=False, label="File",
        help_text=(f"Screenshots: JPG, PNG or WebP, up to {MAXIMUM_IMAGE_BYTES // (1024 * 1024)} MB. "
                   f"Videos: MP4 or WebM, up to {MAXIMUM_VIDEO_BYTES // (1024 * 1024)} MB."),
    )
    video_url = forms.URLField(
        required=False, label="Or a video link", assume_scheme="https",
        help_text="For a video only: a YouTube, Google Drive or Vimeo link instead of uploading the file.",
    )
    visibility = forms.ChoiceField(
        choices=ProjectDocument.Visibility.choices, label="Who can see it in the archive",
        help_text="While the project is running, only you, your supervisor and staff of the department can see it.",
    )

    def __init__(self, *args, parent, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent

    def clean(self):
        cleaned = super().clean()
        kind, upload, link = cleaned.get("kind"), cleaned.get("file"), cleaned.get("video_url")
        if not kind:
            return cleaned
        if kind == ProjectMedia.Kind.IMAGE:
            if link:
                self.add_error("video_url", "A link can only be given for a video.")
            if not upload:
                self.add_error("file", "Choose the image file.")
        elif bool(upload) == bool(link):
            self.add_error("file", "Upload the video file or give a link, not both.")
        try:
            if upload:
                validate_media_upload(upload, kind)
            if link:
                validate_video_link(link)
        except forms.ValidationError as error:
            self.add_error("file" if upload else "video_url", error)
        existing = self.parent.media.filter(kind=kind).count()
        limit = MAXIMUM_IMAGES_PER_PROJECT if kind == ProjectMedia.Kind.IMAGE else MAXIMUM_VIDEOS_PER_PROJECT
        if existing >= limit:
            raise forms.ValidationError(f"This project already has the most {'screenshots' if kind == 'image' else 'videos'} allowed ({limit}). Remove one first.")
        return cleaned


class DeadlineForm(forms.Form):
    name = forms.CharField(max_length=120, label="Deadline", help_text="For example \"Chapter 1: Introduction\".")
    due_date = forms.DateField(label="Due date", widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["semester"] = semester_field(
            "Leave empty for every semester, or type one (like 26A) to give the deadline only to that semester's students.")


class MilestoneForm(forms.Form):
    name = forms.CharField(max_length=120, label="Milestone", help_text="For example \"Working prototype\".")
    due_date = forms.DateField(required=False, label="Due date", widget=forms.DateInput(attrs={"type": "date"}))
