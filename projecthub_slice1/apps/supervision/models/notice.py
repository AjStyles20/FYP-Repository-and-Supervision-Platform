"""Notices a supervisor publishes to their students, with acknowledgement tracking.

A notice can be aimed at one project (that student) or at a whole department. The student's first
view and explicit acknowledgement are both recorded, so "I never saw it" is answerable.
"""

from django.conf import settings
from django.db import models


class Announcement(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="published_announcements",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
        help_text="Leave empty to address the whole department.",
    )
    department = models.ForeignKey(
        "academics.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )
    title = models.CharField(max_length=180)
    body = models.TextField()
    is_pinned = models.BooleanField(default=False)
    requires_acknowledgement = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]
        indexes = [models.Index(fields=["department", "-created_at"])]

    def __str__(self):
        return self.title

    @property
    def audience_label(self):
        if self.project_id:
            return f"For {self.project.student_name}"
        if self.department_id:
            return f"All of {self.department.name}"
        return "Everyone"

    @property
    def acknowledgement_count(self):
        return self.acknowledgements.filter(acknowledged_at__isnull=False).count()


class AnnouncementAcknowledgement(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="acknowledgements")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="announcement_acknowledgements",
    )
    seen_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-acknowledged_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "user"],
                name="uq_announcement_acknowledgement_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user} · {self.announcement.title}"
