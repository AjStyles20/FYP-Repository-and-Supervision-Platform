"""Publishing notices to the active students who need to see them, and personal notifications."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Announcement, Notification

DEFAULT_DEDUP_HOURS = 24


def notify(recipient, kind, obj, *, title, body="", url="", now=None):
    """Create one notification, unless the same (recipient, kind, object) got one in the last 24 hours.

    Returns the new Notification, or None when it was a duplicate. The recipient's user row is locked
    for the check-and-insert, so two automation runs at the same moment cannot both create one.
    """
    now = now or timezone.now()
    window = timedelta(hours=getattr(settings, "NOTIFICATION_DEDUP_HOURS", DEFAULT_DEDUP_HOURS))
    object_type, object_id = obj._meta.label, str(obj.pk)
    with transaction.atomic():
        get_user_model().objects.select_for_update().filter(pk=recipient.pk).first()
        duplicate = Notification.objects.filter(
            recipient=recipient, kind=kind, object_type=object_type, object_id=object_id,
            created_at__gt=now - window,
        ).exists()
        if duplicate:
            return None
        return Notification.objects.create(
            recipient=recipient, kind=kind, object_type=object_type, object_id=object_id,
            title=title[:200], body=body, url=url[:255], created_at=now,
        )


def notify_supervisees(*, author, projects, title, body):
    notices = []
    seen = set()
    for project in projects:
        if project.pk in seen or project.archived or project.supervisor_id != author.pk:
            continue
        seen.add(project.pk)
        notices.append(
            Announcement.objects.create(
                author=author,
                project=project,
                department=project.department,
                title=title,
                body=body,
            )
        )
    return notices
