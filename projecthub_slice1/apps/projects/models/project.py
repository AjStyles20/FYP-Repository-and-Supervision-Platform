"""The project record and its lifecycle history.

A project is what a student is being examined on. It becomes past work only when the Head of Department signs
off completion, which is a separate act from a defence happening (decision D-15).
"""

from django.conf import settings
from django.db import models

from apps.accounts.models import Role


class ProjectStage(models.TextChoices):
    """Ordered stages. Stored values are fixed strings; labels are what people read."""

    PROPOSED = "0", "Topic proposed"
    SUPERVISOR_ACCEPTED = "1", "Supervisor accepted"
    APPROVED = "2", "Approved by the department"
    IN_PROGRESS = "3", "In progress"
    SUBMITTED = "4", "Submitted for examination"
    DEFENDED = "5", "Defended"
    COMPLETED = "6", "Completed and signed off"


STAGE_SEQUENCE = (
    ProjectStage.PROPOSED,
    ProjectStage.SUPERVISOR_ACCEPTED,
    ProjectStage.APPROVED,
    ProjectStage.IN_PROGRESS,
    ProjectStage.SUBMITTED,
    ProjectStage.DEFENDED,
    ProjectStage.COMPLETED,
)

# Stages at which the student is past the proposal conversation.
ACTIVE_STAGES = (
    ProjectStage.SUPERVISOR_ACCEPTED,
    ProjectStage.APPROVED,
    ProjectStage.IN_PROGRESS,
    ProjectStage.SUBMITTED,
    ProjectStage.DEFENDED,
)

SUPERVISOR_CHOICES = {"role__in": [Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN]}


class Project(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": Role.STUDENT},
        related_name="student_projects",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    keywords = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Comma-separated topics, used by repository search.",
    )
    department = models.ForeignKey("academics.Department", on_delete=models.PROTECT, related_name="projects")
    programme = models.ForeignKey("academics.Programme", on_delete=models.PROTECT, related_name="projects")
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_projects",
        limit_choices_to=SUPERVISOR_CHOICES,
    )
    stage = models.CharField(max_length=20, choices=ProjectStage.choices, default=ProjectStage.PROPOSED)
    # Chosen by hand by the coordinator (D-38); empty means "not set yet".
    semester = models.ForeignKey(
        "academics.Semester", on_delete=models.SET_NULL, null=True, blank=True, related_name="projects",
    )

    # Each date is recorded by an authorised person at the moment the step happens.
    approval_date = models.DateField(null=True, blank=True, help_text="Date the department approved the topic.")
    submission_date = models.DateField(null=True, blank=True, help_text="Date the report was submitted.")
    defence_date = models.DateField(null=True, blank=True, help_text="Date the project was defended.")

    continuation_link = models.CharField(max_length=255, blank=True)
    gap_summary = models.TextField(blank=True, help_text="The gap a future student could pick up.")
    archived = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["archived", "-updated_at"]),
            models.Index(fields=["department", "archived"]),
        ]

    def __str__(self):
        return self.title

    @property
    def stage_label(self):
        return self.get_stage_display()

    @property
    def stage_position(self):
        """1-based position in the ordered stage list; 0 if the stored value is unknown."""
        try:
            return STAGE_SEQUENCE.index(self.stage) + 1
        except ValueError:
            return 0

    @property
    def stage_total(self):
        return len(STAGE_SEQUENCE)

    @property
    def is_approved(self):
        return self.stage_position >= STAGE_SEQUENCE.index(ProjectStage.APPROVED) + 1

    @property
    def is_defended(self):
        return self.stage_position >= STAGE_SEQUENCE.index(ProjectStage.DEFENDED) + 1

    @property
    def student_name(self):
        return self.student.get_full_name() or self.student.username

    @property
    def supervisor_name(self):
        if not self.supervisor:
            return ""
        return self.supervisor.get_full_name() or self.supervisor.username

    def stages_with_state(self):
        """Yield (stage, label, state) for the progress track, state in done/current/upcoming."""
        current = self.stage_position
        rows = []
        for index, stage in enumerate(STAGE_SEQUENCE, start=1):
            if index < current:
                state = "done"
            elif index == current:
                state = "current"
            else:
                state = "upcoming"
            rows.append({"stage": stage, "label": ProjectStage(stage).label, "state": state})
        return rows


class StatusEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Project status events are append-only.")

    def delete(self):
        raise PermissionError("Project status events are append-only.")


class ProjectStatusEvent(models.Model):
    """Append-only record of every stage change, who made it and why.

    This is the audit trail behind the project status: the department can show exactly when a
    topic was approved, when it was defended and who recorded it.

    Application code can only add rows: changing or deleting one, singly or through a queryset,
    raises PermissionError. Django's own cascades still work (deleting a project, for example when
    purge_demo removes demo data, removes its events; deleting a user clears `actor`), because
    those bypass these methods. That is deliberate: they remove whole records, not rewrite history.
    """

    objects = StatusEventQuerySet.as_manager()

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="status_events")
    from_stage = models.CharField(max_length=20, choices=ProjectStage.choices, blank=True)
    to_stage = models.CharField(max_length=20, choices=ProjectStage.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_status_events",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "project status event"

    def __str__(self):
        return f"{self.project.title}: {self.get_to_stage_display()}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Project status events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Project status events are append-only.")
