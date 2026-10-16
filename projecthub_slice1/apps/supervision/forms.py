import os

from django import forms
from django.urls import reverse

from apps.accounts.models import SupervisorProfile
from .models import Announcement, MeetingMode, MeetingStatus, MeetingRequest, SharedResource, SupervisorAvailability, SupervisionMeeting
from apps.projects.models import Project


class MeetingForm(forms.ModelForm):
    scheduled_for = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    next_meeting_at = forms.DateTimeField(required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))

    class Meta:
        model = SupervisionMeeting
        fields = ("scheduled_for", "duration_minutes", "venue", "mode", "status", "agenda", "discussion", "corrective_action", "next_steps", "next_meeting_at")
        widgets = {"agenda": forms.Textarea, "discussion": forms.Textarea, "corrective_action": forms.Textarea, "next_steps": forms.Textarea}


class StudentMeetingResponseForm(forms.Form):
    response = forms.ChoiceField(choices=(("confirm", "Confirm this record"), ("dispute", "Dispute this record")))
    comment = forms.CharField(required=False, widget=forms.Textarea)


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ("project", "title", "body", "is_pinned", "requires_acknowledgement")
        labels = {
            "project": "For one student's project (leave empty for the whole department)",
            "body": "Message",
            "is_pinned": "Pin it to the top of the notices",
            "requires_acknowledgement": "Students must confirm they have read it",
        }
        widgets = {"body": forms.Textarea}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].empty_label = "Whole department"
        for name in ("is_pinned", "requires_acknowledgement"):
            self.fields[name].label_suffix = ""  # a tick box reads as a sentence, without a colon


class AvailabilityForm(forms.ModelForm):
    class Meta:
        model = SupervisorAvailability
        fields = ("weekday", "start_time", "end_time", "venue", "mode", "is_active")
        labels = {"weekday": "Day", "venue": "Venue or meeting link", "is_active": "Open for meeting requests"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].label_suffix = ""
        widgets = {"start_time": forms.TimeInput(attrs={"type": "time"}), "end_time": forms.TimeInput(attrs={"type": "time"})}


class ApprovalPolicyForm(forms.ModelForm):
    class Meta:
        model = SupervisorProfile
        fields = ("approval_method", "approval_criteria")
        widgets = {"approval_criteria": forms.Textarea(attrs={"rows": 5})}


class _CurrentFile:
    """The saved file as the edit form shows it: its own name, linked through the checked download view."""

    def __init__(self, file, url):
        self.file, self.url = file, url

    def __str__(self):
        return os.path.basename(self.file.name)


class DownloadLinkFileInput(forms.ClearableFileInput):
    """A file input whose "Currently" link goes through the download view (media files are not served directly)."""

    download_url = ""

    def format_value(self, value):
        value = super().format_value(value)
        if self.download_url and self.is_initial(value):
            return _CurrentFile(value, self.download_url)
        return value


class SharedResourceForm(forms.ModelForm):
    project_targets = forms.ModelMultipleChoiceField(
        queryset=Project.objects.none(),
        label="Send to supervisees",
        help_text="Choose one or more current students. Only your assigned students are listed.",
        widget=forms.SelectMultiple(attrs={"size": 6}),
    )

    class Meta:
        model = SharedResource
        fields = ("title", "description", "url", "file")
        labels = {"url": "Link", "file": "Or upload a file"}
        help_texts = {"url": "A web address, for material that already lives online."}
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "file": DownloadLinkFileInput}

    def __init__(self, *args, supervisor, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.file:
            self.fields["file"].widget.download_url = reverse("download_shared_resource", args=[self.instance.pk])
        targets = Project.objects.filter(supervisor=supervisor, archived=False).select_related("student").order_by("student__last_name", "student__first_name")
        if self.instance and self.instance.pk:
            targets = (targets | self.instance.projects.filter(supervisor=supervisor, archived=False)).distinct()
            self.fields["project_targets"].initial = self.instance.projects.filter(supervisor=supervisor, archived=False)
        self.fields["project_targets"].queryset = targets
        self.fields["project_targets"].label_from_instance = lambda project: (
            f"{project.student.get_full_name() or project.student.username} — {project.title}"
        )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("url") and not cleaned.get("file") and not (self.instance and self.instance.file):
            self.add_error("file", "Upload a file or provide a web address.")
        return cleaned


class MeetingRequestForm(forms.ModelForm):
    class Meta:
        model = MeetingRequest
        fields = ("availability", "requested_date", "message")
        labels = {"availability": "Window", "requested_date": "Date", "message": "What you want to discuss (optional)"}
        widgets = {"requested_date": forms.DateInput(attrs={"type": "date"}), "message": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, availability_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["availability"].queryset = availability_queryset or SupervisorAvailability.objects.none()

    def clean_requested_date(self):
        from django.utils import timezone
        value = self.cleaned_data["requested_date"]
        if value < timezone.localdate():
            raise forms.ValidationError("Choose a future date.")
        return value

    def clean(self):
        cleaned = super().clean()
        slot, requested_date = cleaned.get("availability"), cleaned.get("requested_date")
        if slot and requested_date and requested_date.weekday() != slot.weekday:
            self.add_error("requested_date", "Choose a date that falls on the selected availability day.")
        return cleaned
