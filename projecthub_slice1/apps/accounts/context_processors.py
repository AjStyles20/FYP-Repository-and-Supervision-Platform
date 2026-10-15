"""Template context: site-wide switches the menus need."""

from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

# The university logo is a file the department provides: static/img/baze-logo.svg or
# static/img/baze-logo.png. Without it the header shows the "BU" mark and the welcome page no logo.
LOGO_FILES = ("img/baze-logo.svg", "img/baze-logo.png")


def logo_url():
    name = next((name for name in LOGO_FILES if finders.find(name)), None)
    return static(name) if name else ""


def site_switches(request):
    return {
        "self_registration_open": settings.STUDENT_SELF_REGISTRATION,
        "ui_theme": settings.UI_THEME,
        "brand_logo_url": logo_url(),
        "public_repository": settings.PUBLIC_REPOSITORY,
    }
