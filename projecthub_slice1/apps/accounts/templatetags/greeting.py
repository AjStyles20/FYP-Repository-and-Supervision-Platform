"""{% greeting user %}: "Good afternoon, Dr. Julius".

The server writes the greeting for Lagos time (settings.TIME_ZONE) so the page is right without
JavaScript; static/js/greeting.js then rewrites it from the viewer's own device clock and keeps it
current while the page stays open.
"""

from django import template
from django.utils import timezone

register = template.Library()


def part_of_day(hour):
    """Morning before 12:00, afternoon until 16:59, evening from 17:00. Must match greeting.js."""
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def greeting_name(user):
    """Staff with a title are greeted by title and first name (Dr. Julius); everyone else by first name."""
    first = user.first_name or user.get_username()
    profile = getattr(user, "supervisor_profile", None) if user.has_staff_role else None
    title = profile.title.strip() if profile and profile.title else ""
    return f"{title} {first}" if title else first


@register.inclusion_tag("includes/greeting.html")
def greeting(user):
    return {"salutation": part_of_day(timezone.localtime().hour), "name": greeting_name(user)}
