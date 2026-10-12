"""Publishing notices to the active students who need to see them, and personal notifications."""

from datetime import timedelta

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import Announcement, Notification

DEFAULT_DEDUP_HOURS = 24

logger = logging.getLogger(__name__)


def _email_alert(notification):
    """Send a copy of an alert to the recipient's Baze email. A mail failure never loses the alert."""
    recipient = notification.recipient
    if not getattr(settings, "EMAIL_ALERTS", True) or not recipient.email or recipient.is_demo or not recipient.is_active:
        return
    link = f"{settings.SITE_URL}{notification.url}" if notification.url.startswith("/") else notification.url
    body = "\n\n".join(part for part in (
        f"Hello {recipient.first_name or 'there'},", notification.title, notification.body,
        f"Open it here: {link}" if link else "", "Baze Project Hub",
    ) if part)
    try:
        send_mail(notification.title, body, settings.DEFAULT_FROM_EMAIL, [recipient.email])
    except Exception:  # the in-app alert stays; the email is only a copy
        logger.warning("Alert email to %s could not be sent", recipient.email, exc_info=True)


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
        notification = Notification.objects.create(
            recipient=recipient, kind=kind, object_type=object_type, object_id=object_id,
            title=title[:200], body=body, url=url[:255], created_at=now,
        )
    # Emailed once the alert is safely saved, so a rolled-back action sends nothing.
    transaction.on_commit(lambda: _email_alert(notification))
    return notification


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
