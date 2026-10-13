"""Milestones a supervisor and student track together, and the faculty's common deadlines (D-33).

A coordinator sets deadlines for the whole faculty (e.g. "Chapter 1" due 15 March); every running
project of the faculty gets a milestone linked to each deadline, and so does every project started
later. A supervisor adds extra milestones for one student and marks any milestone done. Overdue
milestones feed the health score.
"""

from django.conf import settings
from django.db import models

from .project import Project


class ProjectDeadline(models.Model):
    faculty = models.ForeignKey("academics.Faculty", on_delete=models.CASCADE, related_name="project_deadlines")
    name = models.CharField(max_length=120, help_text="For example \"Chapter 1: Introduction\".")
    due_date = models.DateField()
    semester = models.ForeignKey(
        "academics.Semester", on_delete=models.SET_NULL, null=True, blank=True, related_name="deadlines",
        help_text="Only projects of this semester get the deadline. Empty: every running project.",
    )
    position = models.PositiveSmallIntegerField(default=0, help_text="Display order.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_project_deadlines"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "position", "id"]

    def __str__(self):
        return f"{self.name} · {self.due_date:%d %b %Y}"


class ProjectMilestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    deadline = models.ForeignKey(
        ProjectDeadline, on_delete=models.SET_NULL, null=True, blank=True, related_name="milestones",
        help_text="Set when the milestone comes from a faculty deadline.",
    )
    name = models.CharField(max_length=120)
    due_date = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    at_risk = models.BooleanField(default=False, help_text="Flagged when the student is falling behind here.")
    position = models.PositiveSmallIntegerField(default=0, help_text="Display order within the project.")

    class Meta:
        ordering = ["due_date", "position", "id"]

    def __str__(self):
        return f"{self.project.title} · {self.name}"
