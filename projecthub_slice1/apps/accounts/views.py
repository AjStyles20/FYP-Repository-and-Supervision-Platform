from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ProjectAuthenticationForm, StudentRegistrationForm
from .models import Role, StudentProfile, User
from .permissions import role_required


def home(request):
    return redirect("dashboard" if request.user.is_authenticated else "login")


class ProjectLoginView(LoginView):
    authentication_form = ProjectAuthenticationForm
    template_name = "registration/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_demo_credentials"] = settings.DEBUG
        return context


def register_student(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = StudentRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except IntegrityError:
            form.add_error(None, "An account already exists with this email address or student ID.")
        else:
            messages.success(
                request,
                "Your registration has been submitted for review. You can sign in after an administrator approves your account.",
            )
            return redirect("login")
    return render(request, "registration/register.html", {"form": form})


@login_required
def dashboard(request):
    return render(request, "dashboard.html", {"role": request.user.role})


@role_required(Role.ADMIN)
def admin_tools(request):
    pending_students = (
        User.objects.filter(
            role=Role.STUDENT,
            is_demo=False,
            student_profile__registration_status=StudentProfile.RegistrationStatus.PENDING,
        )
        .select_related("department", "student_profile__programme")
        .order_by("date_joined")
    )
    return render(request, "admin_tools.html", {"pending_students": pending_students})


@role_required(Role.ADMIN)
@require_POST
def review_student_registration(request, user_id):
    action = request.POST.get("action")
    if action not in {"approve", "reject"}:
        return HttpResponseBadRequest("Choose whether to approve or reject this registration.")

    with transaction.atomic():
        student = get_object_or_404(
            User.objects.select_for_update(),
            pk=user_id,
            role=Role.STUDENT,
            is_demo=False,
            student_profile__registration_status=StudentProfile.RegistrationStatus.PENDING,
        )
        registration = student.student_profile
        registration.registration_status = (
            StudentProfile.RegistrationStatus.APPROVED
            if action == "approve"
            else StudentProfile.RegistrationStatus.REJECTED
        )
        registration.save(update_fields=["registration_status"])
        student.is_active = action == "approve"
        student.save(update_fields=["is_active"])
    outcome = "Approved" if action == "approve" else "Rejected"
    messages.success(request, f"{outcome} the account for {student.get_full_name() or student.email}.")
    return redirect("admin_tools")


def permission_denied_view(request, exception=None):
    return render(request, "403.html", status=403)
