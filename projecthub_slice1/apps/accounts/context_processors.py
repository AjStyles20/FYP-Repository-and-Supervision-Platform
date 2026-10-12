"""Template context: site-wide switches the menus need."""

from django.conf import settings


def site_switches(request):
    return {"self_registration_open": settings.STUDENT_SELF_REGISTRATION, "ui_theme": settings.UI_THEME}
