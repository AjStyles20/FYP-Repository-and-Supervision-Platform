"""Scheduled supervision meetings and the record of what happened.

The record is two-party. The supervisor schedules the meeting and records attendance and what was
discussed; the student confirms the record is accurate. Both sides can always see the attendance
count, which is the whole point: it settles "I did turn up" arguments without either side having
to take the other's word for it.

Meeting discussions and corrective actions are private to the student, the assigned supervisor
and authorised academic staff (D-14). They are never rendered on public project pages.
"""

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator

from apps.projects.models import Project


class MeetingMode(models.TextChoices):
    PHYSICAL = "physical", "In person"
    ONLINE = "online", "Online"
    HYBRID = "hybrid", "Hybrid"


class MeetingStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    HELD = "held", "Held"
    CANCELLED = "cancelled", "Cancelled"
    MISSED = "missed", "Missed"


class SupervisorAvailability(models.Model):
    WEEKDAY_CHOICES = (
        (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
        (4, "Friday"), (5, "Saturday"), (6, "Sunday"),
    )
    supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availability_slots")
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES, validators=[MinValueValidator(0), MaxValueValidator(6)])
    start_time = models.TimeField()
    end_time = models.TimeField()
    venue = models.CharField(max_length=160, blank=True)
    mode = models.CharField(max_length=20, choices=MeetingMode.choices, default=MeetingMode.PHYSICAL)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["weekday", "start_time"]

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "End time must be after start time."})
        if self.is_active and self.supervisor_id and self.start_time and self.end_time:
            overlaps = SupervisorAvailability.objects.filter(
                supervisor_id=self.supervisor_id, weekday=self.weekday, is_active=True,
                start_time__lt=self.end_time, end_time__gt=self.start_time,
            )
            if self.pk:
                overlaps = overlaps.exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError("This slot overlaps another active availability slot.")

    def __str__(self):
        return f"{self.supervisor} · {self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"

    def get_weekday_display(self):
        import calendar
        return calendar.day_name[self.weekday]


class MeetingRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="meeting_requests")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meeting_requests")
    availability = models.ForeignKey(SupervisorAvailability, on_delete=models.PROTECT, related_name="requests")
    requested_date = models.DateField()
    message = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_meeting_requests")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, help_text="The supervisor's reason when declining.")
    meeting = models.OneToOneField("SupervisionMeeting", on_delete=models.SET_NULL, null=True, blank=True, related_name="request")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "requested_date", "created_at"]

    def clean(self):
        if self.student_id and self.project_id and self.student_id != self.project.student_id:
            raise ValidationError("Only the project's student can request a meeting.")
        if self.availability_id and self.project_id and self.availability.supervisor_id != self.project.supervisor_id:
            raise ValidationError("The availability slot does not belong to this project's supervisor.")
        if self.availability_id and self.requested_date and self.requested_date.weekday() != self.availability.weekday:
            raise ValidationError({"requested_date": "Choose a date that falls on the selected availability day."})


class SupervisionMeeting(models.Model):
    DURATION_CHOICES = ((30, "30 minutes"), (45, "45 minutes"), (60, "1 hour"), (90, "1 hour 30 minutes"), (120, "2 hours"))

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="meetings")
    scheduled_for = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60, choices=DURATION_CHOICES)
    venue = models.CharField(max_length=160, blank=True, help_text="Room, building or meeting link.")
    mode = models.CharField(max_length=20, choices=MeetingMode.choices, default=MeetingMode.PHYSICAL)
    status = models.CharField(max_length=20, choices=MeetingStatus.choices, default=MeetingStatus.SCHEDULED)

    agenda = models.TextField(blank=True, help_text="What the supervisor intends to cover.")
    discussion = models.TextField(blank=True, help_text="What was actually discussed.")
    corrective_action = models.TextField(blank=True, help_text="What the student must do before the next meeting.")
    next_steps = models.TextField(blank=True, help_text="Agreed next steps and who owns them.")
    next_meeting_at = models.DateTimeField(null=True, blank=True)

    scheduled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_meetings",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_meetings",
    )

    # Both parties confirm the same record; a disagreement is visible rather than silent.
    student_confirmed_at = models.DateTimeField(null=True, blank=True)
    student_disputed_at = models.DateTimeField(null=True, blank=True)
    student_comment = models.TextField(blank=True, help_text="The student's note on this record.")
    supervisor_confirmed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_for"]
        indexes = [
            models.Index(fields=["project", "-scheduled_for"]),
            models.Index(fields=["status", "scheduled_for"]),
        ]

    def __str__(self):
        return f"{self.project.title} · {self.scheduled_for:%d %b %Y %H:%M}"

    @property
    def was_held(self):
        return self.status == MeetingStatus.HELD

    @property
    def is_confirmed_by_student(self):
        return self.student_confirmed_at is not None

    @property
    def is_confirmed_by_supervisor(self):
        return self.supervisor_confirmed_at is not None

    @property
    def is_fully_confirmed(self):
        return self.is_confirmed_by_student and self.is_confirmed_by_supervisor

    @property
    def status_label(self):
        return self.get_status_display()


class MeetingRecordEdit(models.Model):
    """A version row for every change to a meeting record, so edits stay visible.

    The change set is stored as JSON: {"field": {"from": ..., "to": ...}}.
    """

    meeting = models.ForeignKey(SupervisionMeeting, on_delete=models.CASCADE, related_name="edits")
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_record_edits",
    )
    edited_at = models.DateTimeField(auto_now_add=True)
    changes = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-edited_at"]

    def __str__(self):
        return f"Edit to {self.meeting} at {self.edited_at:%d %b %Y %H:%M}"
