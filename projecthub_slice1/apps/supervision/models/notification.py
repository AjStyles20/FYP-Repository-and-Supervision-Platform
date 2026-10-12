"""Personal notifications, one row per recipient, created through services.notify().

Shown as "Alerts" in the interface, because the student menu already uses "Notifications" for
supervisor notices. The run_automation command is the main writer. (recipient, kind, object) is what
notify() checks so the same alert is not sent twice within NOTIFICATION_DEDUP_HOURS.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationKind(models.TextChoices):
    AT_RISK_PROJECT = "at_risk_project", "Project at risk"
    PENDING_REGISTRATION = "pending_registration", "Registration waiting"
    UNACKNOWLEDGED_NOTICE = "unacknowledged_notice", "Notice not acknowledged"
    ACCOUNT_APPROVED = "account_approved", "Account approved"
    MEETING_REQUESTED = "meeting_requested", "Meeting requested"
    MEETING_REQUEST_DECIDED = "meeting_request_decided", "Meeting request answered"
    DEADLINE_SOON = "deadline_soon", "Deadline coming up"
    PROPOSAL_SUBMITTED = "proposal_submitted", "Proposal submitted"


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=40, choices=NotificationKind.choices)
    object_type = models.CharField(max_length=100, help_text="Model label of the flagged record, e.g. projects.Project.")
    object_id = models.CharField(max_length=64)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=255, blank=True, help_text="Where the recipient can act on it.")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["recipient", "kind", "object_type", "object_id", "created_at"], name="notification_dedup_idx"),
            models.Index(fields=["recipient", "read_at"], name="notification_unread_idx"),
        ]

    def __str__(self):
        return f"{self.recipient} · {self.title}"

    @property
    def is_read(self):
        return self.read_at is not None
