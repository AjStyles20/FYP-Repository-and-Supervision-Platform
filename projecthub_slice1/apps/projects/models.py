from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from django.utils import timezone

from apps.academics.models import Department, Programme
from apps.accounts.models import Role


class ProjectStage(models.TextChoices):
    PROPOSED = "0", "Proposed"
    SUPERVISOR_ACCEPTED = "1", "Supervisor accepted"
    APPROVED = "2", "Approved"
    IN_PROGRESS = "3", "In progress"
    SUBMITTED = "4", "Submitted"
    DEFENDED = "5", "Defended"
    COMPLETED = "6", "Completed"


class Project(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": Role.STUDENT},
        related_name="student_projects",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="projects")
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="projects")
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_projects",
        limit_choices_to={"role__in": [Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN]},
    )
    stage = models.CharField(max_length=20, choices=ProjectStage.choices, default=ProjectStage.PROPOSED)
    approval_date = models.DateField(null=True, blank=True)
    continuation_link = models.CharField(max_length=255, blank=True)
    gap_summary = models.TextField(blank=True)
    archived = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title

    @property
    def stage_label(self):
        return self.get_stage_display()


class ProjectSupervisorAssignment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="supervisor_assignments")
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="project_supervisor_assignments",
        limit_choices_to={"role__in": [Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN]},
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_supervisor_assignments",
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    change_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(ended_at__isnull=True),
                name="one_current_supervisor_per_project",
            )
        ]

    def __str__(self):
        return f"{self.project.title} · {self.supervisor}"


class ProjectMilestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(max_length=120)
    done = models.BooleanField(default=False)
    at_risk = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.project.title} · {self.name}"


class ProjectMeetingLog(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="meeting_logs")
    meeting_date = models.DateField()
    attended = models.BooleanField(default=True)
    discussion = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-meeting_date"]

    def __str__(self):
        return f"{self.project.title} · {self.meeting_date}"


class ArchivedProject(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    year = models.PositiveSmallIntegerField()
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="archived_projects")
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="archived_projects")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="archived_projects",
        limit_choices_to={"role": Role.STUDENT},
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_supervisions",
        limit_choices_to={"role__in": [Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN]},
    )
    previous_supervisors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="previous_archived_supervisions",
        limit_choices_to={"role__in": [Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN]},
    )
    gap_summary = models.TextField(blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "-created_at"]

    def __str__(self):
        return self.title


def validate_project_document_size(upload):
    maximum_size = 25 * 1024 * 1024
    if upload.size > maximum_size:
        raise ValidationError("Project files must be 25 MB or smaller.")


class ProjectDocument(models.Model):
    class Visibility(models.TextChoices):
        BAZE_USERS = "baze_users", "All signed-in Baze users"
        STAFF_ONLY = "staff_only", "Academic staff only"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
    )
    archived_project = models.ForeignKey(
        ArchivedProject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
    )
    title = models.CharField(max_length=180)
    file = models.FileField(
        upload_to="project_documents/%Y/%m/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "zip"]
            ),
            validate_project_document_size,
        ],
    )
    visibility = models.CharField(
        max_length=12,
        choices=Visibility.choices,
        default=Visibility.BAZE_USERS,
    )
    is_demo = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(project__isnull=False, archived_project__isnull=True)
                    | Q(project__isnull=True, archived_project__isnull=False)
                ),
                name="project_document_exactly_one_parent",
            )
        ]

    def __str__(self):
        return self.title
