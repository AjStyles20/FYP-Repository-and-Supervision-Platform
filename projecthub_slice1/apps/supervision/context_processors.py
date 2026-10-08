"""Template context: the signed-in user's unread notification count, for the "Alerts" menu link."""

from .models import Notification


def notifications(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_notification_count": Notification.objects.filter(recipient=user, read_at__isnull=True).count()}
