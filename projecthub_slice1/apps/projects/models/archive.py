"""Past work: a project that the Head of Department has signed off and archived.

An archived record is a snapshot. It keeps its own copy of the facts a reader needs even if the
student account changes later: title, abstract, dates, award, the final supervisor, the earlier
supervisors and the documented gap a future student could pick up.

Graduation is deliberately *not* stored here. Project completion and university graduation are
separate facts (D-15); the verified graduation year lives on the student profile.
"""

from django.conf import settings
from django.db import models

from apps.accounts.models import Role

from .project import Project, SUPERVISOR_CHOICES


class ArchivedProject(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    keywords = models.CharField(max_length=255, blank=True, default="")

    year = models.PositiveSmallIntegerField(help_text="Archive year, used for the repository year filter.")
    completed_on = models.DateField(null=True, blank=True, help_text="Date the Head of Department signed completion off.")
    defence_date = models.DateField(null=True, blank=True)
    semester = models.ForeignKey(
        "academics.Semester", on_delete=models.SET_NULL, null=True, blank=True, related_name="archived_projects",
        help_text="The project's semester, kept even when sign-off falls in the next calendar year.",
    )

    department = models.ForeignKey("academics.Department", on_delete=models.PROTECT, related_name="archived_projects")
    programme = models.ForeignKey("academics.Programme", on_delete=models.PROTECT, related_name="archived_projects")
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
        limit_choices_to=SUPERVISOR_CHOICES,
    )
    previous_supervisors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="previous_archived_supervisions",
        limit_choices_to=SUPERVISOR_CHOICES,
    )

    gap_summary = models.TextField(blank=True, help_text="What was left undone, for the next student.")
    continuation_link = models.CharField(max_length=255, blank=True, default="")
    archive_note = models.TextField(blank=True, default="", help_text="How completion was confirmed before archiving.")

    source_project = models.OneToOneField(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archive_record",
        help_text="The live project this record was created from, when there was one.",
    )
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "-created_at"]
        indexes = [
            models.Index(fields=["year"]),
            models.Index(fields=["department", "-year"]),
        ]

    def __str__(self):
        return self.title

    @property
    def student_name(self):
        return self.student.get_full_name() or self.student.username

    @property
    def supervisor_name(self):
        if not self.supervisor:
            return ""
        return self.supervisor.get_full_name() or self.supervisor.username

    @property
    def award(self):
        return self.programme.award

    @property
    def earlier_supervisors(self):
        return list(self.previous_supervisors.all())

    @property
    def student_profile(self):
        return getattr(self.student, "student_profile", None)
