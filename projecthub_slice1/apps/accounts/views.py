from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.academics.models import Programme
from apps.audit.models import AuditEvent
from apps.audit.services import log_event
from apps.projects.models import ArchivedProject, Project, ProjectCompletion, ProjectStage
from apps.projects.services.counters import staff_with_counters
from apps.projects.services.health import HEALTH_PREFETCH, health_score
from apps.supervision.models import (
    Announcement, AnnouncementAcknowledgement, Notification, SharedResource, SupervisionMeeting, student_resource_scope,
)
from apps.supervision.models import NotificationKind
from apps.supervision.services import notify

from .forms import (
    AddStudentForm, ContactDetailsForm, ProjectAuthenticationForm, StudentEditForm, StaffAccountForm, StaffEditForm, StudentRegistrationForm, active_admin_count,
    generate_temporary_password,
)
from .models import STAFF_ROLES, Role, StudentProfile, SupervisorProfile, User
from .permissions import role_required


def home(request):
    """The logged-out home page; signed-in people go straight to their portal."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "home.html", _welcome_figures())


def _welcome_figures():
    """Totals and the faculty list for the welcome page: numbers only, nothing about any person.

    Real rows only, unless the database holds no real projects at all (the demo), so a real
    deployment never shows sample data to visitors and the demo does not show zeros.
    """
    from django.db.models import Count

    from apps.academics.models import Faculty

    include_demo = not (Project.objects.filter(is_demo=False).exists() or ArchivedProject.objects.filter(is_demo=False).exists())
    real = Q() if include_demo else Q(is_demo=False)
    archived = ArchivedProject.objects.filter(real)
    faculties = (
        Faculty.objects.filter(real)
        .annotate(
            department_count=Count("departments", filter=None if include_demo else Q(departments__is_demo=False), distinct=True),
            archived_count=Count("departments__archived_projects", distinct=True,
                                 filter=None if include_demo else Q(departments__archived_projects__is_demo=False)),
        )
        .order_by("name")
    )
    return {
        "figures": {
            "archived": archived.count(),
            "running": Project.objects.filter(real, archived=False).count(),
            "staff": User.objects.filter(real, is_active=True, role__in=(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD)).count(),
            "faculties": len(faculties),
        },
        "faculties": faculties,
    }


class ProjectLoginView(LoginView):
    authentication_form = ProjectAuthenticationForm
    template_name = "registration/login.html"


def register_student(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if not settings.STUDENT_SELF_REGISTRATION:
        # D-28: accounts are created by an administrator or the department's coordinator.
        return render(request, "registration/closed.html")

    form = StudentRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            student = form.save()
        except IntegrityError:
            form.add_error(None, "An account already exists with this email address or student identification number.")
        else:
            messages.success(request, "Your registration has been submitted for review.")
            return redirect("registration_status", token=registration_status_token(student))
    return render(request, "registration/register.html", {"form": form})


REGISTRATION_STATUS_SALT = "accounts.registration-status"


def registration_status_token(student):
    """A signed, tamper-proof token naming one registration. Only the person who just registered
    receives it, so the status page needs no email lookup (which would reveal who is registered)."""
    return signing.dumps(student.pk, salt=REGISTRATION_STATUS_SALT)


def _registration_for_token(token):
    max_age = int(getattr(settings, "REGISTRATION_STATUS_MAX_AGE_DAYS", 30)) * 24 * 3600
    try:
        pk = signing.loads(token, salt=REGISTRATION_STATUS_SALT, max_age=max_age)
    except signing.BadSignature:  # also covers SignatureExpired
        return None
    return User.objects.filter(pk=pk, role=Role.STUDENT).select_related("student_profile").first()


def _rejection_reason(student):
    event = AuditEvent.objects.filter(
        action="account.registration_reject", object_type="accounts.User", object_id=str(student.pk)
    ).order_by("-created_at").first()
    return (event.details or {}).get("reason", "") if event else ""


@require_GET
def registration_status(request, token):
    """Pending / approved / rejected for the registration named by a signed token.

    ?format=json returns {"status": ..., "reason": ...} for the page's 30-second poller.
    """
    student = _registration_for_token(token)
    profile = getattr(student, "student_profile", None) if student else None
    if profile is None:
        if request.GET.get("format") == "json":
            return JsonResponse({"detail": "This status link is not valid."}, status=404)
        return render(request, "registration/status.html", {"invalid": True}, status=404)
    status = profile.registration_status
    reason = _rejection_reason(student) if status == StudentProfile.RegistrationStatus.REJECTED else ""
    if request.GET.get("format") == "json":
        response = JsonResponse({"status": status, "reason": reason})
    else:
        response = render(request, "registration/status.html", {
            "student": student, "status": status, "reason": reason, "token": token,
        })
    response["Cache-Control"] = "no-store"
    return response


@login_required
def dashboard(request):
    user = request.user
    if user.role == Role.STUDENT:
        profile = getattr(user, "student_profile", None)
        if profile and profile.student_status == StudentProfile.Status.GRADUATED:
            return _alumni_portal_response(request, profile)
        return _student_portal_response(request, profile)

    if user.role == Role.SUPERVISOR:
        return render(request, "portals/supervisor.html", _supervisor_portal_context(user))
    if user.role == Role.COORDINATOR:
        return render(request, "portals/coordinator.html", _department_portal_context(user))
    if user.role == Role.HOD:
        return render(request, "portals/hod.html", _hod_portal_context(user))
    return render(request, "portals/admin.html", _admin_portal_context(user))


@role_required(Role.STUDENT)
def student_portal(request):
    profile = getattr(request.user, "student_profile", None)
    if profile and profile.student_status == StudentProfile.Status.GRADUATED:
        return redirect("alumni_portal")
    return _student_portal_response(request, profile)


@role_required(Role.STUDENT)
def alumni_portal(request):
    profile = getattr(request.user, "student_profile", None)
    if not profile or profile.student_status != StudentProfile.Status.GRADUATED:
        return redirect("student_portal")
    return _alumni_portal_response(request, profile)


def _student_portal_response(request, profile):
    project = (
        Project.objects.filter(student=request.user, archived=False)
        .select_related("department__faculty", "programme", "supervisor")
        .first()
    )
    upcoming_meeting = None
    recent_meetings = []
    if project:
        upcoming_meeting = project.meetings.filter(
            status="scheduled", scheduled_for__gte=timezone.now()
        ).order_by("scheduled_for").first()
        recent_meetings = project.meetings.exclude(status="scheduled").order_by("-scheduled_for")[:3]
    announcements = Announcement.objects.filter(
        Q(project__student=request.user)
        | Q(project__isnull=True, department_id=profile.programme.department_id)
        | Q(project__isnull=True, department__isnull=True)
    ) if profile else Announcement.objects.none()
    announcements = announcements.select_related("author").annotate(
        already_seen=Exists(AnnouncementAcknowledgement.objects.filter(
            announcement_id=OuterRef("pk"), user=request.user, seen_at__isnull=False
        )),
        acknowledged=Exists(AnnouncementAcknowledgement.objects.filter(
            announcement_id=OuterRef("pk"), user=request.user, acknowledged_at__isnull=False
        )),
    ).order_by("-is_pinned", "-created_at")
    unread_notice_count = announcements.filter(already_seen=False).count()
    shared_resources = (
        SharedResource.objects.filter(student_resource_scope(request.user))
        .select_related("author").distinct().order_by("-created_at")
    )
    completed_projects = ArchivedProject.objects.filter(student=request.user).order_by("-year")
    return render(
        request,
        "portals/student_current.html",
        {
            "role": Role.STUDENT,
            "student_profile": profile,
            "project": project,
            "upcoming_meeting": upcoming_meeting,
            "archived_projects": completed_projects[:3],
            "is_project_complete": bool(profile and profile.student_status == StudentProfile.Status.FYP_COMPLETED),
            "recent_meetings": recent_meetings,
            "student_notices": announcements[:4],
            "unread_notice_count": unread_notice_count,
            "student_resources": shared_resources[:4],
        },
    )


def _alumni_portal_response(request, profile):
    archived_projects = ArchivedProject.objects.filter(student=request.user).select_related(
        "department__faculty", "programme", "supervisor"
    ).prefetch_related("previous_supervisors").order_by("-year")
    return render(
        request,
        "portals/student_alumni.html",
        {"role": Role.STUDENT, "student_profile": profile, "archived_projects": archived_projects},
    )


def for_viewer(queryset, user):
    """The counter rule: a demo account counts demo and real rows; a real account counts real rows only.

    Used by the portal counters, /api/summary/ and the lists beside them, so a number and its list
    always agree. Review pages in apps/projects/views.py do not use it yet (docs/known_limits.md).
    """
    return queryset if user.is_demo else queryset.filter(is_demo=False)


def _department_projects(user):
    projects = for_viewer(Project.objects.filter(archived=False), user)
    if user.department_id:
        projects = projects.filter(department_id=user.department_id)
    else:
        projects = projects.none()
    return projects.select_related("student", "supervisor", "programme", "department")


def _department_health_rows(projects, limit=8):
    """The coordinator's view of project health: highest risk first."""
    rows = [{"project": project, "health": health_score(project)} for project in projects.prefetch_related(*HEALTH_PREFETCH)]
    rows = [row for row in rows if row["health"] is not None]
    rows.sort(key=lambda row: (-row["health"].score, row["project"].title))
    return rows[:limit]


def department_counts(user):
    """The four coordinator portal counters. Shared by the portal page and /api/summary/."""
    projects = _department_projects(user)
    return {
        "active_count": projects.count(),
        "unassigned_count": projects.filter(supervisor__isnull=True).count(),
        "approval_count": projects.filter(stage=ProjectStage.SUPERVISOR_ACCEPTED).count(),
        "defence_count": projects.filter(stage=ProjectStage.SUBMITTED).count(),
    }


def _department_portal_context(user):
    projects = _department_projects(user)
    pending_proposals = projects.filter(stage=ProjectStage.PROPOSED)
    awaiting_logging = projects.filter(stage=ProjectStage.SUPERVISOR_ACCEPTED)
    awaiting_defence_record = projects.filter(stage=ProjectStage.SUBMITTED)
    return {
        "role": Role.COORDINATOR,
        "department": user.department,
        **department_counts(user),
        "pending_proposal_count": pending_proposals.count(),
        "queue_projects": (pending_proposals | awaiting_logging | awaiting_defence_record).order_by("updated_at")[:6],
        "health_rows": _department_health_rows(projects),
        "supervisor_load": staff_with_counters(department=user.department)[:6] if user.department_id else [],
    }


def _supervisor_portal_context(user):
    projects = Project.objects.filter(supervisor=user, archived=False).select_related(
        "student", "programme", "department"
    ).order_by("student__last_name", "student__first_name")
    upcoming_meetings = SupervisionMeeting.objects.filter(
        project__supervisor=user, project__archived=False,
        status="scheduled", scheduled_for__gte=timezone.now(),
    ).select_related("project", "project__student").order_by("scheduled_for")[:5]
    return {
        "role": Role.SUPERVISOR,
        "department": user.department,
        "projects": projects[:8],
        "active_count": projects.count(),
        "proposal_count": projects.filter(stage=ProjectStage.PROPOSED, approval_form__student_signed_on__isnull=False).count(),
        "approved_count": projects.filter(stage__in=(ProjectStage.APPROVED, ProjectStage.IN_PROGRESS, ProjectStage.SUBMITTED, ProjectStage.DEFENDED)).count(),
        "defended_count": projects.filter(stage=ProjectStage.DEFENDED).count(),
        "upcoming_meetings": upcoming_meetings,
        "past_count": ArchivedProject.objects.filter(Q(supervisor=user) | Q(previous_supervisors=user)).distinct().count(),
    }


def _hod_portal_context(user):
    projects = _department_projects(user)
    signoff_queue = projects.filter(stage=ProjectStage.DEFENDED).order_by("updated_at")
    graduation_checks = ProjectCompletion.objects.filter(
        project__department_id=user.department_id, graduation_verified=False
    ) if user.department_id else ProjectCompletion.objects.none()
    archived_count = ArchivedProject.objects.filter(department_id=user.department_id).count() if user.department_id else 0
    return {
        "role": Role.HOD,
        "department": user.department,
        "active_count": projects.count(),
        "signoff_count": signoff_queue.count(),
        "graduation_check_count": graduation_checks.count(),
        "archived_count": archived_count,
        "signoff_projects": signoff_queue[:6],
        "supervisor_load": staff_with_counters(department=user.department)[:6] if user.department_id else [],
    }


def _pending_registrations(user):
    return for_viewer(User.objects.filter(
        role=Role.STUDENT,
        student_profile__registration_status=StudentProfile.RegistrationStatus.PENDING,
    ), user)


def admin_counts(user):
    """The four admin portal counters for this viewer. Shared by the portal page and /api/summary/."""
    return {
        "pending_count": _pending_registrations(user).count(),
        "student_count": for_viewer(User.objects.filter(role=Role.STUDENT, is_active=True), user).count(),
        "staff_count": for_viewer(User.objects.filter(role__in=(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD), is_active=True), user).count(),
        "programme_count": for_viewer(Programme.objects.all(), user).count(),
    }


def _admin_portal_context(user):
    pending_students = _pending_registrations(user).select_related("department", "student_profile__programme").order_by("date_joined")
    return {
        "role": Role.ADMIN,
        "pending_students": pending_students[:5],
        **admin_counts(user),
    }


SUMMARY_COUNTERS = {Role.ADMIN: admin_counts, Role.COORDINATOR: department_counts}


@require_GET
def api_summary(request):
    """Live numbers for the signed-in user: counts only, never names or emails.

    Admins and coordinators get their portal counters plus their unread alerts; every other role
    gets only its own unread alert count. 401 when signed out. The shape is documented in
    docs/explain/live-counters.md; static/js/live-counters.js polls it every 30 seconds.
    """
    if not request.user.is_authenticated:
        response = JsonResponse({"detail": "Sign in required."}, status=401)
    else:
        summary = {"role": request.user.role}
        if request.user.role in SUMMARY_COUNTERS:
            summary["counters"] = SUMMARY_COUNTERS[request.user.role](request.user)
        summary["unread_notifications"] = Notification.objects.filter(recipient=request.user, read_at__isnull=True).count()
        summary["generated_at"] = timezone.now().isoformat()
        response = JsonResponse(summary)
    response["Cache-Control"] = "no-store"
    return response


@login_required
def my_contact(request):
    """Everyone keeps their own personal email and phone number up to date, and chooses who sees each."""
    form = ContactDetailsForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your contact details are saved.")
        return redirect("my_contact")
    return render(request, "accounts/contact.html", {"form": form})


@role_required(Role.ADMIN)
def admin_tools(request):
    pending_students = (
        _pending_registrations(request.user)
        .select_related("department", "student_profile__programme")
        .order_by("date_joined")
    )
    staff_accounts = (
        User.objects.filter(role__in=(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN))
        .select_related("department").order_by("role", "last_name", "first_name", "username")
    )
    query = request.GET.get("q", "").strip()
    found_students = (
        for_viewer(User.objects.filter(role=Role.STUDENT), request.user)
        .filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
                | Q(username__icontains=query) | Q(student_profile__student_number__icontains=query))
        .select_related("student_profile__programme").order_by("last_name", "first_name")[:25]
    ) if query else []
    return render(request, "admin_tools.html", {
        "pending_students": pending_students, "staff_accounts": staff_accounts,
        "student_query": query, "found_students": found_students,
    })


@role_required(Role.ADMIN)
def manage_student_account(request, user_id):
    """Correct a student's details, reset their password, or deactivate or reactivate the account."""
    student = get_object_or_404(
        for_viewer(User.objects.filter(role=Role.STUDENT, student_profile__isnull=False), request.user)
        .select_related("student_profile__programme__department"),
        pk=user_id,
    )
    profile = student.student_profile
    approved = profile.registration_status == StudentProfile.RegistrationStatus.APPROVED
    action = request.POST.get("action", "") if request.method == "POST" else ""
    form = StudentEditForm(request.POST if action == "save" else None, student=student)
    name = student.get_full_name() or student.username

    if action == "save" and form.is_valid():
        changes = form.save()
        if changes:
            log_event(actor=request.user, action="account.student_updated", summary=f"Updated student account {student.username}", obj=student, details=changes)
            messages.success(request, f"Saved the changes to {name}.")
            if "email" in changes:
                messages.info(request, f"They now sign in with {student.email}.")
                if not _email_sign_in_change(request, student):
                    messages.warning(request, f"The change is saved, but the notice to {student.email} could not be sent. Please tell them directly.")
        else:
            messages.info(request, "Nothing changed.")
        return redirect("manage_student_account", user_id=student.pk)

    if action == "reset_password":
        password = generate_temporary_password()
        student.set_password(password)
        student.must_change_password = True
        student.save(update_fields=["password", "must_change_password"])
        log_event(actor=request.user, action="account.password_reset", summary=f"Reset the password for {student.username}", obj=student)
        response = render(request, "accounts/staff_created.html", {
            "staff": student, "temporary_password": password, "is_reset": True,
            "back_url": reverse("manage_student_account", args=[student.pk]),
        })
        response["Cache-Control"] = "no-store"
        return response

    if action == "deactivate" and student.is_active:
        student.is_active = False
        student.save(update_fields=["is_active"])
        log_event(actor=request.user, action="account.student_deactivated", summary=f"Deactivated student account {student.username}", obj=student)
        messages.success(request, f"{name} can no longer sign in. Their records are kept.")
        return redirect("manage_student_account", user_id=student.pk)

    if action == "reactivate" and not student.is_active:
        if not approved:
            # Pending and rejected registrations are decided on the review list, not switched on here.
            messages.error(request, "This registration has not been approved. Approve it from the registrations list instead.")
        else:
            student.is_active = True
            student.save(update_fields=["is_active"])
            log_event(actor=request.user, action="account.student_reactivated", summary=f"Reactivated student account {student.username}", obj=student)
            messages.success(request, f"{name} can sign in again.")
        return redirect("manage_student_account", user_id=student.pk)

    if request.method == "POST" and action != "save":
        return HttpResponseBadRequest("Unknown action.")
    return render(request, "accounts/student_manage.html", {
        "student": student, "profile": profile, "form": form, "approved": approved,
        "has_project": student.student_projects.exists(),
    })


@role_required(Role.ADMIN)
def add_staff_account(request):
    """Create a staff account. The temporary password is shown once on the result page, never logged."""
    form = StaffAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user, password = form.save()
        log_event(
            actor=request.user, action="account.staff_created",
            summary=f"Created {user.get_role_display()} account for {user.email}", obj=user,
            details={"role": user.role, "department": user.department.name if user.department else "",
                     "can_assign_supervisors": user.can_assign_supervisors},
        )
        response = render(request, "accounts/staff_created.html", {"staff": user, "temporary_password": password})
        response["Cache-Control"] = "no-store"  # the page holds a password: keep it out of the browser cache
        return response
    return render(request, "accounts/staff_form.html", {"form": form})


@role_required(Role.ADMIN, Role.COORDINATOR)
def add_student_account(request):
    """An administrator (any department) or a coordinator (own department) creates a student account.

    The temporary password is shown once on the result page and never logged (D-28).
    """
    if request.user.role == Role.COORDINATOR and not request.user.department_id:
        raise PermissionDenied
    form = AddStudentForm(request.POST or None, creator=request.user)
    if request.method == "POST" and form.is_valid():
        student, password = form.save()
        log_event(
            actor=request.user, action="account.student_created",
            summary=f"Created student account for {student.email}", obj=student,
            details={"student_number": student.student_profile.student_number,
                     "programme": str(student.student_profile.programme)},
        )
        response = render(request, "accounts/staff_created.html", {
            "staff": student, "temporary_password": password,
            "back_url": reverse("admin_tools") if request.user.role == Role.ADMIN else reverse("supervisor_assignments"),
            "back_label": "Back to admin tools" if request.user.role == Role.ADMIN else "Back to student allocation",
            "add_another_url": reverse("add_student_account"),
        })
        response["Cache-Control"] = "no-store"  # the page holds a password: keep it out of the browser cache
        return response
    return render(request, "accounts/student_form.html", {"form": form})


@role_required(Role.ADMIN)
def manage_staff_account(request, user_id):
    """Edit a staff account, deactivate or reactivate it, or reset its password."""
    staff = get_object_or_404(User.objects.select_related("department"), pk=user_id, role__in=STAFF_ROLES)
    action = request.POST.get("action", "") if request.method == "POST" else ""
    form = StaffEditForm(request.POST if action == "save" else None, staff=staff, editor=request.user)
    name = staff.get_full_name() or staff.username

    if action == "save" and form.is_valid():
        changes = form.save()
        if changes:
            log_event(actor=request.user, action="account.staff_updated", summary=f"Updated staff account {staff.username}", obj=staff, details=changes)
            messages.success(request, f"Saved the changes to {staff.get_full_name() or staff.username}.")
            if "email" in changes:
                messages.info(request, f"They now sign in with {staff.email}.")
                if not _email_sign_in_change(request, staff):
                    messages.warning(request, f"The change is saved, but the notice to {staff.email} could not be sent. Please tell them directly.")
        else:
            messages.info(request, "Nothing changed.")
        return redirect("manage_staff_account", user_id=staff.pk)

    if action == "deactivate":
        if staff.pk == request.user.pk:
            messages.error(request, "You cannot deactivate your own account.")
        elif staff.role == Role.ADMIN and active_admin_count(exclude=staff) == 0:
            messages.error(request, "This is the only active administrator; create another one first.")
        elif staff.is_active:
            staff.is_active = False
            staff.save(update_fields=["is_active"])
            log_event(actor=request.user, action="account.staff_deactivated", summary=f"Deactivated staff account {staff.username}", obj=staff)
            messages.success(request, f"{name} can no longer sign in. Their records are kept.")
        return redirect("manage_staff_account", user_id=staff.pk)

    if action == "reactivate" and not staff.is_active:
        staff.is_active = True
        staff.save(update_fields=["is_active"])
        log_event(actor=request.user, action="account.staff_reactivated", summary=f"Reactivated staff account {staff.username}", obj=staff)
        messages.success(request, f"{name} can sign in again.")
        return redirect("manage_staff_account", user_id=staff.pk)

    if action == "reset_password":
        password = generate_temporary_password()
        staff.set_password(password)
        staff.must_change_password = True
        staff.save(update_fields=["password", "must_change_password"])
        log_event(actor=request.user, action="account.password_reset", summary=f"Reset the password for {staff.username}", obj=staff)
        response = render(request, "accounts/staff_created.html", {"staff": staff, "temporary_password": password, "is_reset": True})
        response["Cache-Control"] = "no-store"
        return response

    if request.method == "POST" and action not in {"save"}:
        return HttpResponseBadRequest("Unknown action.")
    return render(request, "accounts/staff_manage.html", {
        "staff": staff, "form": form, "is_self": staff.pk == request.user.pk,
        "active_supervisions": staff.supervised_projects.filter(archived=False).count(),
    })


DEPARTMENT_STAFF_ACTIONS = {
    "make_coordinator": ("role", Role.COORDINATOR),
    "make_supervisor": ("role", Role.SUPERVISOR),
    "grant_allocation": ("can_assign_supervisors", True),
    "remove_allocation": ("can_assign_supervisors", False),
}


@role_required(Role.HOD)
def department_staff(request):
    """The Head of Department appoints the final-year project coordinator and the lecturers who allocate supervisors (D-19).

    Only supervisors and coordinators in the Head of Department's own department can be changed, and only between
    those two roles; accounts themselves are still created by the system administrator.
    """
    hod = request.user
    staff = User.objects.filter(
        department_id=hod.department_id, role__in=(Role.SUPERVISOR, Role.COORDINATOR), is_active=True,
    ).order_by("last_name", "first_name", "username") if hod.department_id else User.objects.none()
    if request.method == "POST":
        change = DEPARTMENT_STAFF_ACTIONS.get(request.POST.get("action", ""))
        if change is None:
            return HttpResponseBadRequest("Unknown action.")
        member = get_object_or_404(staff, pk=request.POST.get("user_id"))
        field, value = change
        before = getattr(member, field)
        if before != value:
            setattr(member, field, value)
            member.save(update_fields=[field])
            if field == "role":
                SupervisorProfile.objects.get_or_create(user=member)  # coordinators can still supervise
            log_event(actor=hod, action="account.staff_updated", summary=f"Updated staff account {member.username}",
                      obj=member, details={field: {"from": str(before), "to": str(value)}})
            name = member.get_full_name() or member.username
            messages.success(request, {
                "make_coordinator": f"{name} is now the final-year project coordinator for the department.",
                "make_supervisor": f"{name} is now a supervisor (no longer coordinator).",
                "grant_allocation": f"{name} can now assign supervisors in the department.",
                "remove_allocation": f"{name} can no longer assign supervisors.",
            }[request.POST["action"]])
        return redirect("department_staff")
    return render(request, "accounts/department_staff.html", {
        "staff": staff,
        "coordinator_count": sum(1 for member in staff if member.role == Role.COORDINATOR),
        "department": hod.department,
    })


class FirstPasswordChangeView(PasswordChangeView):
    """Any signed-in user can change their password here; a temporary password must be changed first."""

    template_name = "registration/password_change.html"
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.user.must_change_password:
            self.request.user.must_change_password = False
            self.request.user.save(update_fields=["must_change_password"])
            log_event(actor=self.request.user, action="account.password_set", summary="Replaced the temporary password", obj=self.request.user)
        messages.success(self.request, "Your password has been changed.")
        return response


@role_required(Role.ADMIN)
@require_POST
def review_student_registration(request, user_id):
    action = request.POST.get("action")
    if action not in {"approve", "reject"}:
        return HttpResponseBadRequest("Choose whether to approve or reject this registration.")
    outcome = "Approved" if action == "approve" else "Rejected"

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
        reason = request.POST.get("reason", "").strip()[:500] if action == "reject" else ""
        log_event(actor=request.user, action=f"account.registration_{action}", summary=f"{outcome} student registration for {student.username}", obj=student,
                  details={"reason": reason} if reason else None)
    messages.success(request, f"{outcome} the account for {student.get_full_name() or student.email}.")
    if action == "approve":
        # Waiting in their Alerts the first time they sign in (a rejected account cannot sign in).
        notify(student, NotificationKind.ACCOUNT_APPROVED, student,
               title="Welcome to Baze Project Hub",
               body="Your registration was approved. Start your final-year project from My project.",
               url=reverse("my_project"))
    if not _email_registration_decision(request, student, approved=action == "approve", reason=reason):
        messages.warning(request, f"The decision is saved, but the email to {student.email} could not be sent. Please tell the student directly.")
    return redirect("admin_tools")


def _email_sign_in_change(request, person):
    """Tell someone their sign-in email was changed, at the new address. Returns False if sending failed."""
    body = (f"Hello {person.first_name or 'there'},\n\nAn administrator changed the email you use to sign in to "
            f"Baze Project Hub. From now on, sign in with {person.email} at:\n"
            f"{request.build_absolute_uri(reverse('login'))}\n\nYour password has not changed. If you did not expect "
            "this, contact the system administrator.\n\nBaze Project Hub")
    try:
        send_mail("Your Baze Project Hub sign-in email has changed", body, settings.DEFAULT_FROM_EMAIL, [person.email])
    except Exception:  # a mail outage must not undo the change
        return False
    return True


def _email_registration_decision(request, student, *, approved, reason=""):
    """Tell the student the outcome at their Baze email. Returns False if sending failed."""
    name = student.first_name or "there"
    if approved:
        subject = "Your Baze Project Hub account is approved"
        body = (f"Hello {name},\n\nYour Baze Project Hub registration has been approved. You can now sign in "
                f"with your Baze email at:\n{request.build_absolute_uri(reverse('login'))}\n\n"
                "Baze Project Hub")
    else:
        subject = "Your Baze Project Hub registration was not approved"
        body = (f"Hello {name},\n\nYour Baze Project Hub registration was not approved."
                + (f"\n\nReason: {reason}" if reason else "")
                + "\n\nIf you think this is a mistake, contact your department.\n\nBaze Project Hub")
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [student.email])
    except Exception:  # a mail outage must not undo the decision
        return False
    return True


@role_required(Role.ADMIN)
def audit_log(request):
    events = AuditEvent.objects.select_related("actor")
    action = request.GET.get("action", "").strip()
    if action:
        events = events.filter(action=action)
    return render(request, "audit/log.html", {"events": events[:200], "actions": AuditEvent.objects.values_list("action", flat=True).distinct().order_by("action"), "selected_action": action})


def permission_denied_view(request, exception=None):
    return render(request, "403.html", status=403)
