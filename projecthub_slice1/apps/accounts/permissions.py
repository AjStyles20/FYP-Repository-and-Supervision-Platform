"""Server-side permission helpers. Deny by default: use these on every view that is not public."""
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Allow only logged-in users whose role is in `roles`; everyone else gets 403 (or the login page)."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def role_or_public_required(*roles):
    """Like role_required, but a visitor who is not logged in is let through while
    settings.PUBLIC_REPOSITORY is on (D-42). Only the completed-project pages use it."""

    def decorator(view):
        guarded = role_required(*roles)(view)

        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated and settings.PUBLIC_REPOSITORY:
                return view(request, *args, **kwargs)
            return guarded(request, *args, **kwargs)

        return wrapper

    return decorator
