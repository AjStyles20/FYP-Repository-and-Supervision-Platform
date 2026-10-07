"""The running student log: where this project actually is right now.

Either side writes entries. The supervisor records what was agreed and what is outstanding; the
student records what they have done and what is blocking them. Everything in the log is visible to
the student, the assigned supervisor and authorised academic staff, which is deliberate: the log is
the shared answer to "where are we", not a private set of staff notes.
"""

from django.conf import settings
from django.db import models


class LogKind(models.TextChoices):
    UPDATE = "update", "Progress update"
    CONCERN = "concern", "Concern"
    ACTION = "action", "Action required"
    DECISION = "decision", "Decision"


class SupervisionLogEntry(models.Model):
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="log_entries")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supervision_log_entries",
    )
    kind = models.CharField(max_length=20, choices=LogKind.choices, default=LogKind.UPDATE)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "supervision log entries"
        indexes = [models.Index(fields=["project", "-created_at"])]

    def __str__(self):
        return f"{self.project.title} · {self.get_kind_display()}"

    @property
    def is_alert(self):
        return self.kind in (LogKind.CONCERN, LogKind.ACTION)

    @property
    def author_name(self):
        return self.author.get_full_name() or self.author.username
