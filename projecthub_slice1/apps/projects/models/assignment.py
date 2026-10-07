"""Who supervises a project, and the history of every change.

A project has exactly one current supervisor. Reassignments never overwrite: the previous row is
closed with an end date and a new row is opened, so the department keeps a full audit trail.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .project import Project, SUPERVISOR_CHOICES


class ProjectSupervisorAssignment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="supervisor_assignments")
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="project_supervisor_assignments",
        limit_choices_to=SUPERVISOR_CHOICES,
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
        indexes = [models.Index(fields=["supervisor", "ended_at"])]

    def __str__(self):
        return f"{self.project.title} · {self.supervisor}"

    @property
    def is_current(self):
        return self.ended_at is None

    @property
    def supervisor_name(self):
        return self.supervisor.get_full_name() or self.supervisor.username
