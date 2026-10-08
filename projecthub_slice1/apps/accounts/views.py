from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
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
    return render(request, "portals/admin.html", _admin_portal_context())


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


def _department_projects(user):
    projects = Project.objects.filter(archived=False)
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
        "proposal_count": projects.filter(stage=ProjectStage.PROPOSED).count(),
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


def _pending_registrations():
    return User.objects.filter(
        role=Role.STUDENT,
        is_demo=False,
        student_profile__registration_status=StudentProfile.RegistrationStatus.PENDING,
    )


def admin_counts():
    """The four admin portal counters. Shared by the portal page and /api/summary/."""
    return {
        "pending_count": _pending_registrations().count(),
        "student_count": User.objects.filter(role=Role.STUDENT, is_active=True, is_demo=False).count(),
        "staff_count": User.objects.filter(role__in=(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD), is_active=True, is_demo=False).count(),
        "programme_count": Programme.objects.count(),
    }


def _admin_portal_context():
    pending_students = _pending_registrations().select_related("department", "student_profile__programme").order_by("date_joined")
    return {
        "role": Role.ADMIN,
        "pending_students": pending_students[:5],
        **admin_counts(),
    }


SUMMARY_COUNTERS = {Role.ADMIN: lambda user: admin_counts(), Role.COORDINATOR: department_counts}


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
        log_event(actor=request.user, action=f"account.registration_{action}", summary=f"{outcome} student registration for {student.username}", obj=student)
    messages.success(request, f"{outcome} the account for {student.get_full_name() or student.email}.")
    return redirect("admin_tools")


@role_required(Role.ADMIN)
def audit_log(request):
    events = AuditEvent.objects.select_related("actor")
    action = request.GET.get("action", "").strip()
    if action:
        events = events.filter(action=action)
    return render(request, "audit/log.html", {"events": events[:200], "actions": AuditEvent.objects.values_list("action", flat=True).distinct().order_by("action"), "selected_action": action})


def permission_denied_view(request, exception=None):
    return render(request, "403.html", status=403)
