"""Send anyone signed in with a temporary password to the password page until they choose their own."""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and getattr(user, "must_change_password", False):
            allowed = {reverse("password_change"), reverse("logout")}
            static_prefix = "/" + settings.STATIC_URL.lstrip("/")
            if request.path not in allowed and not request.path.startswith(static_prefix):
                return redirect("password_change")
        return self.get_response(request)
