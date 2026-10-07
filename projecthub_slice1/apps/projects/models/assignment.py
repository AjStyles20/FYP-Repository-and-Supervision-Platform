"""Who supervises a project, and the history of every change.

A project has exactly one current supervisor. Reassignments never overwrite: the previous row is
closed with an end date and a new row is opened, so the department keeps a full audit trail.

How "one current supervisor" is enforced by the database, on MySQL as well as SQLite:
MySQL ignores unique constraints that have a condition (Django warning models.W036), so a rule like
"project is unique where ended_at is NULL" would silently not exist there. Instead each row has
`is_current`, which is True while the assignment is open and NULL once it has ended. A plain unique
constraint on (project, is_current) then allows any number of ended rows (NULLs never clash) but only
one True row per project. A check constraint keeps `is_current` and `ended_at` in step.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .project import Project, SUPERVISOR_CHOICES


def _current_flag(ended_at):
    return True if ended_at is None else None


class AssignmentQuerySet(models.QuerySet):
    """Keeps `is_current` in step when rows are changed in bulk, which skips save()."""

    def update(self, **kwargs):
        if "ended_at" in kwargs and "is_current" not in kwargs:
            kwargs["is_current"] = _current_flag(kwargs["ended_at"])
        return super().update(**kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            obj.is_current = _current_flag(obj.ended_at)
        return super().bulk_create(objs, *args, **kwargs)


class ProjectSupervisorAssignment(models.Model):
    objects = AssignmentQuerySet.as_manager()

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
    # True while this is the project's current supervisor, NULL once ended. Set by save(); never edit it.
    is_current = models.BooleanField(null=True, blank=True, default=True, editable=False)

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(fields=["project", "is_current"], name="one_current_supervisor_per_project_v2"),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True, is_current=True) | Q(ended_at__isnull=False, is_current__isnull=True),
                name="assignment_is_current_matches_ended_at",
            ),
        ]
        indexes = [models.Index(fields=["supervisor", "ended_at"])]

    def __str__(self):
        return f"{self.project.title} · {self.supervisor}"

    def save(self, *args, **kwargs):
        self.is_current = _current_flag(self.ended_at)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "ended_at" in update_fields:
            kwargs["update_fields"] = {*update_fields, "is_current"}
        super().save(*args, **kwargs)

    @property
    def supervisor_name(self):
        return self.supervisor.get_full_name() or self.supervisor.username
