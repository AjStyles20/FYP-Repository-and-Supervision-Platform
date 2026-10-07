"""Milestones a supervisor and student agree on, and track together."""

from django.db import models

from .project import Project


class ProjectMilestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(max_length=120)
    due_date = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)
    at_risk = models.BooleanField(default=False, help_text="Flagged when the student is falling behind here.")
    position = models.PositiveSmallIntegerField(default=0, help_text="Display order within the project.")

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.project.title} · {self.name}"
