from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from pathlib import Path
from datetime import date, datetime, timedelta
from django.http import FileResponse, Http404

from apps.audit.services import log_event
from apps.accounts.models import Role, StudentProfile, SupervisorProfile
from apps.accounts.permissions import role_required
from apps.projects.files import open_stored_file
from apps.projects.models import Project

from .forms import (
    ApprovalPolicyForm, AvailabilityForm, AnnouncementForm, MeetingForm, MeetingRequestForm, SharedResourceForm,
    StudentMeetingResponseForm,
)
from .models import (
    Announcement, AnnouncementAcknowledgement, MeetingRecordEdit, MeetingRequest, Notification, NotificationKind,
    SharedResource,
    SupervisorAvailability, SupervisionMeeting, student_resource_scope,
)
from .services import notify, notify_supervisees

MEETING_EDIT_FIELDS = (
    "scheduled_for", "duration_minutes", "venue", "mode", "status", "agenda", "discussion",
    "corrective_action", "next_steps", "next_meeting_at",
)


def _has_schedule_conflict(*, supervisor, scheduled_for, duration_minutes, exclude_meeting_id=None):
    new_end = scheduled_for + timedelta(minutes=duration_minutes)
    meetings = SupervisionMeeting.objects.filter(
        project__supervisor=supervisor,
        status="scheduled",
    )
    if exclude_meeting_id:
        meetings = meetings.exclude(pk=exclude_meeting_id)
    return any(
        scheduled_for < (meeting.scheduled_for + timedelta(minutes=meeting.duration_minutes))
        and new_end > meeting.scheduled_for
        for meeting in meetings
    )


def _project_access(user, project):
    """Who may read a project's meeting records (R-33).

    The student, their assigned supervisor, and the coordinator or Head of Department of the project's
    department. Other supervisors in the department and system administrators may not.
    """
    if user.role == Role.STUDENT:
        return project.student_id == user.pk
    if project.supervisor_id == user.pk:
        return True
    return (
        user.role in (Role.COORDINATOR, Role.HOD)
        and user.department_id is not None
        and user.department_id == project.department_id
    )


def _meeting_editor(user, project):
    return user.role in (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD) and project.supervisor_id == user.pk


@transaction.atomic
def _save_meeting_record(meeting, form, actor):
    old = {field: getattr(meeting, field) for field in MEETING_EDIT_FIELDS}
    updated = form.save(commit=False)
    updated.recorded_by = actor
    updated.student_confirmed_at = None
    updated.student_comment = ""
    updated.supervisor_confirmed_at = None
    updated.save()
    changes = {}
    for field in MEETING_EDIT_FIELDS:
        new = getattr(updated, field)
        if old[field] != new:
            changes[field] = {"from": old[field].isoformat() if hasattr(old[field], "isoformat") else old[field],
                              "to": new.isoformat() if hasattr(new, "isoformat") else new}
    if changes:
        MeetingRecordEdit.objects.create(meeting=updated, edited_by=actor, changes=changes)
    return updated


def _slot_duration(slot):
    """The longest standard meeting length that fits in an availability window (at least 30 minutes)."""
    minutes = (datetime.combine(date.min, slot.end_time) - datetime.combine(date.min, slot.start_time)).seconds // 60
    fitting = [value for value, _ in SupervisionMeeting.DURATION_CHOICES if value <= minutes]
    return max(fitting) if fitting else 30


def _request_meeting(request, project, form):
    """The student asks for a meeting in one of their supervisor's availability windows (D-32)."""
    if not form.is_valid():
        return False
    meeting_request = form.save(commit=False)
    meeting_request.project, meeting_request.student = project, request.user
    slot, day = meeting_request.availability, meeting_request.requested_date
    try:
        meeting_request.full_clean()
    except ValidationError as error:
        for field, errors in error.message_dict.items():
            form.add_error(field if field in form.fields else None, errors)
        return False
    start = timezone.make_aware(datetime.combine(day, slot.start_time))
    if MeetingRequest.objects.filter(project=project, availability=slot, requested_date=day,
                                     status=MeetingRequest.Status.PENDING).exists():
        form.add_error(None, "You have already asked for this time; wait for your supervisor's answer.")
        return False
    if _has_schedule_conflict(supervisor=project.supervisor, scheduled_for=start, duration_minutes=_slot_duration(slot)):
        form.add_error(None, "Your supervisor already has a meeting at that time. Choose another date or window.")
        return False
    meeting_request.save()
    notify(project.supervisor, NotificationKind.MEETING_REQUESTED, meeting_request,
           title=f"Meeting request from {request.user.get_full_name() or request.user.username}",
           body=f"{slot.get_weekday_display()} {day:%d %B %Y} at {slot.start_time:%H:%M}. {meeting_request.message}".strip(),
           url=reverse("project_meetings", args=[project.pk]))
    log_event(actor=request.user, action="meeting.requested", summary=f"Meeting requested for {project.title}", obj=meeting_request)
    messages.success(request, "Request sent. You will get an alert when your supervisor answers.")
    return True


@transaction.atomic
def _decide_meeting_request(request, project):
    """The supervisor accepts a request (it becomes a scheduled meeting) or declines it with a reason."""
    meeting_request = get_object_or_404(
        MeetingRequest.objects.select_for_update().select_related("availability"),
        pk=request.POST.get("request_id"), project=project, status=MeetingRequest.Status.PENDING,
    )
    decision, note = request.POST.get("decision"), request.POST.get("note", "").strip()[:1000]
    slot = meeting_request.availability
    if decision == "decline":
        if not note:
            messages.error(request, "Give the student a reason when declining.")
            return
        meeting_request.status = MeetingRequest.Status.DECLINED
        outcome = f"declined: {note}"
    elif decision == "accept":
        start = timezone.make_aware(datetime.combine(meeting_request.requested_date, slot.start_time))
        duration = _slot_duration(slot)
        if _has_schedule_conflict(supervisor=request.user, scheduled_for=start, duration_minutes=duration):
            messages.error(request, "You already have a meeting at that time. Decline the request with a new time suggestion.")
            return
        meeting = SupervisionMeeting.objects.create(
            project=project, scheduled_for=start, duration_minutes=duration, venue=slot.venue, mode=slot.mode,
            agenda=meeting_request.message, scheduled_by=request.user, recorded_by=request.user,
        )
        MeetingRecordEdit.objects.create(meeting=meeting, edited_by=request.user, changes={"created": {"to": "Meeting scheduled from the student's request"}})
        meeting_request.status, meeting_request.meeting = MeetingRequest.Status.APPROVED, meeting
        outcome = f"accepted: {start:%A %d %B %Y at %H:%M}, {slot.venue or slot.get_mode_display()}"
    else:
        raise PermissionDenied
    meeting_request.decision_note, meeting_request.reviewed_by, meeting_request.reviewed_at = note, request.user, timezone.now()
    meeting_request.save()
    notify(project.student, NotificationKind.MEETING_REQUEST_DECIDED, meeting_request,
           title=f"Your meeting request was {meeting_request.get_status_display().lower()}",
           body=f"Your supervisor {outcome}.", url=reverse("project_meetings", args=[project.pk]))
    log_event(actor=request.user, action=f"meeting.request_{decision}ed", summary=f"Meeting request {decision}ed for {project.title}", obj=meeting_request)
    messages.success(request, "Request accepted; the meeting is scheduled." if decision == "accept" else "Request declined; your student was told why.")


@login_required
def project_meetings(request, project_id):
    project = get_object_or_404(Project.objects.select_related("student", "supervisor", "department"), pk=project_id)
    if not _project_access(request.user, project):
        raise PermissionDenied
    can_schedule = request.user.role in (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD) and project.supervisor_id == request.user.pk
    is_owner = request.user.role == Role.STUDENT and project.student_id == request.user.pk
    slots = SupervisorAvailability.objects.filter(supervisor=project.supervisor, is_active=True) if project.supervisor_id else SupervisorAvailability.objects.none()
    action = request.POST.get("action", "schedule") if request.method == "POST" else ""
    request_form = MeetingRequestForm(request.POST if action == "request_meeting" else None, availability_queryset=slots)
    if action == "request_meeting":
        if not is_owner or project.archived or not project.supervisor_id:
            raise PermissionDenied
        if _request_meeting(request, project, request_form):
            return redirect("project_meetings", project_id=project.pk)
    elif action == "decide_request":
        if not can_schedule:
            raise PermissionDenied
        _decide_meeting_request(request, project)
        return redirect("project_meetings", project_id=project.pk)
    form = MeetingForm(request.POST if action == "schedule" else None)
    if action == "schedule":
        if not can_schedule:
            raise PermissionDenied
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.project = project
            meeting.scheduled_by = request.user
            meeting.recorded_by = request.user
            collision = meeting.status == "scheduled" and _has_schedule_conflict(
                supervisor=request.user,
                scheduled_for=meeting.scheduled_for,
                duration_minutes=meeting.duration_minutes,
            )
            if collision:
                form.add_error("scheduled_for", "This time overlaps another scheduled meeting. Choose an available time.")
            else:
                meeting.save()
                MeetingRecordEdit.objects.create(meeting=meeting, edited_by=request.user, changes={"created": {"to": "Meeting scheduled"}})
                notify_supervisees(
                    author=request.user,
                    projects=[project],
                    title="A supervision meeting was scheduled",
                    body=f"Your supervisor scheduled a meeting for {meeting.scheduled_for:%A, %d %B %Y at %H:%M} for {meeting.duration_minutes} minutes. Venue: {meeting.venue or meeting.get_mode_display()}.",
                )
                log_event(actor=request.user, action="meeting.scheduled", summary=f"Meeting scheduled for {project.title}", obj=meeting)
                messages.success(request, "Meeting scheduled. Your student has an in-app notification.")
                return redirect("project_meetings", project_id=project.pk)
    meetings = project.meetings.select_related("scheduled_by", "recorded_by").prefetch_related("edits")
    counts = {
        "held": project.meetings.filter(status="held").count(),
        "missed": project.meetings.filter(status="missed").count(),
    }
    meeting_requests = project.meeting_requests.select_related("availability").order_by("-created_at")
    return render(request, "supervision/meetings.html", {
        "project": project, "meetings": meetings, "form": form, "can_schedule": can_schedule, "counts": counts,
        "can_request": is_owner and not project.archived and slots.exists(), "request_form": request_form,
        "is_owner": is_owner, "meeting_requests": meeting_requests,
        "pending_requests": [item for item in meeting_requests if item.status == MeetingRequest.Status.PENDING] if can_schedule else [],
    })


@login_required
def meeting_detail(request, meeting_id):
    meeting = get_object_or_404(SupervisionMeeting.objects.select_related("project", "project__student", "project__supervisor"), pk=meeting_id)
    project = meeting.project
    if not _project_access(request.user, project):
        raise PermissionDenied
    response_form = StudentMeetingResponseForm(request.POST or None)
    if request.method == "POST":
        if request.user.role == Role.STUDENT and project.student_id == request.user.pk:
            if response_form.is_valid():
                meeting.student_comment = response_form.cleaned_data["comment"]
                if response_form.cleaned_data["response"] == "confirm":
                    meeting.student_confirmed_at = timezone.now()
                    meeting.student_disputed_at = None
                else:
                    meeting.student_confirmed_at = None
                    meeting.student_disputed_at = timezone.now()
                meeting.save(update_fields=["student_confirmed_at", "student_disputed_at", "student_comment", "updated_at"])
                log_event(actor=request.user, action=f"meeting.student_{response_form.cleaned_data['response']}d", summary=f"Student response for {project.title}", obj=meeting)
                messages.success(request, "Your response has been recorded.")
                return redirect("meeting_detail", meeting_id=meeting.pk)
        elif request.user.pk == project.supervisor_id:
            meeting.supervisor_confirmed_at = timezone.now()
            meeting.save(update_fields=["supervisor_confirmed_at", "updated_at"])
            log_event(actor=request.user, action="meeting.supervisor_confirmed", summary=f"Supervisor confirmed meeting record for {project.title}", obj=meeting)
            messages.success(request, "Your confirmation has been recorded.")
            return redirect("meeting_detail", meeting_id=meeting.pk)
        else:
            raise PermissionDenied
    return render(request, "supervision/meeting_detail.html", {"meeting": meeting, "form": response_form})


@login_required
def edit_meeting(request, meeting_id):
    meeting = get_object_or_404(SupervisionMeeting.objects.select_related("project"), pk=meeting_id)
    if not _meeting_editor(request.user, meeting.project):
        raise PermissionDenied
    form = MeetingForm(request.POST or None, instance=meeting)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["status"] == "scheduled" and _has_schedule_conflict(
            supervisor=request.user,
            scheduled_for=form.cleaned_data["scheduled_for"],
            duration_minutes=form.cleaned_data["duration_minutes"],
            exclude_meeting_id=meeting.pk,
        ):
            form.add_error("scheduled_for", "This time overlaps another scheduled meeting. Choose an available time.")
            return render(request, "supervision/meeting_edit.html", {"meeting": meeting, "form": form})
        old_schedule = (meeting.scheduled_for, meeting.duration_minutes, meeting.venue, meeting.mode, meeting.status)
        meeting = _save_meeting_record(meeting, form, request.user)
        new_schedule = (meeting.scheduled_for, meeting.duration_minutes, meeting.venue, meeting.mode, meeting.status)
        if meeting.status == "scheduled" and new_schedule != old_schedule:
            notify_supervisees(
                author=request.user,
                projects=[meeting.project],
                title="A supervision meeting was updated",
                body=f"Your supervisor updated the meeting to {meeting.scheduled_for:%A, %d %B %Y at %H:%M} for {meeting.duration_minutes} minutes. Venue: {meeting.venue or meeting.get_mode_display()}.",
            )
        log_event(actor=request.user, action="meeting.record_edited", summary=f"Meeting record edited for {meeting.project.title}", obj=meeting)
        messages.success(request, "Meeting record updated; previous versions are retained.")
        return redirect("meeting_detail", meeting_id=meeting.pk)
    return render(request, "supervision/meeting_edit.html", {"meeting": meeting, "form": form})


@login_required
def announcements(request):
    if request.user.role == Role.STUDENT:
        project_ids = Project.objects.filter(student=request.user).values_list("id", flat=True)
        profile = getattr(request.user, "student_profile", None)
        if not profile or profile.student_status == StudentProfile.Status.GRADUATED:
            rows = Announcement.objects.none()
        else:
            department = profile.programme.department
            rows = Announcement.objects.filter(
                Q(project_id__in=project_ids)
                | Q(project__isnull=True, department=department)
                | Q(project__isnull=True, department__isnull=True)
            )
    elif request.user.role in (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD):
        rows = Announcement.objects.filter(Q(project__supervisor=request.user) | Q(department=request.user.department) | Q(department__isnull=True))
    else:
        rows = Announcement.objects.all()
    rows = rows.select_related("project", "department", "author")
    notice_cards = []
    for notice in rows:
        if notice.author_id == request.user.pk:
            # The author is not part of their own notice's audience: no "seen" stamp, no acknowledge button.
            notice_cards.append({"notice": notice, "acknowledgement": None, "is_author": True})
            continue
        acknowledgement, _ = AnnouncementAcknowledgement.objects.get_or_create(announcement=notice, user=request.user)
        if acknowledgement.seen_at is None:
            acknowledgement.seen_at = timezone.now()
            acknowledgement.save(update_fields=["seen_at"])
        notice_cards.append({"notice": notice, "acknowledgement": acknowledgement})
    form = AnnouncementForm(request.POST or None)
    can_post = request.user.role == Role.SUPERVISOR and bool(request.user.department_id)
    allowed_projects = Project.objects.filter(supervisor=request.user, archived=False) if can_post else Project.objects.none()
    form.fields["project"].queryset = allowed_projects
    resource_form = SharedResourceForm(
        request.POST or None,
        request.FILES or None,
        supervisor=request.user,
    ) if can_post else None
    resource_rows = SharedResource.objects.filter(author=request.user).prefetch_related("projects__student") if can_post else []
    if request.method == "POST" and request.POST.get("action") == "publish_resource":
        if not can_post:
            raise PermissionDenied
        resource_form = SharedResourceForm(request.POST, request.FILES, supervisor=request.user)
        if resource_form.is_valid():
            resource, targets = _save_shared_resource(resource_form, request.user)
            notify_supervisees(
                author=request.user,
                projects=targets,
                title=f"New shared resource: {resource.title}",
                body="Your supervisor shared a new file or guide. Open Notices and resources to download it.",
            )
            log_event(actor=request.user, action="resource.published", summary=f"Shared resource published: {resource.title}", obj=resource)
            messages.success(request, "Resource uploaded and students were notified.")
            return redirect("announcements")
    if request.method == "POST" and request.POST.get("action") == "publish":
        if not can_post:
            raise PermissionDenied
        form = AnnouncementForm(request.POST)
        form.fields["project"].queryset = allowed_projects
        if form.is_valid():
            notice = form.save(commit=False)
            notice.author = request.user
            if notice.project_id:
                if notice.project.supervisor_id != request.user.pk:
                    raise PermissionDenied
                notice.department = notice.project.department
            else:
                notice.department_id = request.user.department_id
            notice.save()
            log_event(actor=request.user, action="notice.published", summary=f"Notice published: {notice.title}", obj=notice)
            messages.success(request, "Notice published.")
            return redirect("announcements")
    if request.method == "POST" and request.POST.get("action") == "acknowledge":
        notice = get_object_or_404(rows, pk=request.POST.get("notice_id"))
        if not notice.requires_acknowledgement or notice.author_id == request.user.pk:
            raise PermissionDenied
        acknowledgement, _ = AnnouncementAcknowledgement.objects.get_or_create(announcement=notice, user=request.user)
        if acknowledgement.acknowledged_at is None:
            acknowledgement.acknowledged_at = timezone.now()
            acknowledgement.save(update_fields=["acknowledged_at"])
            log_event(actor=request.user, action="notice.acknowledged", summary=f"Notice acknowledged: {notice.title}", obj=notice)
        messages.success(request, "Notice acknowledgement saved.")
        return redirect("announcements")
    return render(request, "supervision/announcements.html", {
        "notice_cards": notice_cards,
        "form": form,
        "can_post": can_post,
        "resource_form": resource_form,
        "resource_rows": resource_rows,
    })


def _save_shared_resource(form, author):
    # `department` is kept for staff scoping only; students see a resource through `projects`.
    resource = form.save(commit=False)
    resource.author = author
    resource.project = None
    resource.department = author.department
    resource.save()
    form.save_m2m()
    targets = list(form.cleaned_data["project_targets"])
    resource.projects.set(targets)
    return resource, targets


@role_required(Role.SUPERVISOR)
def edit_shared_resource(request, resource_id):
    resource = get_object_or_404(SharedResource, pk=resource_id, author=request.user)
    form = SharedResourceForm(request.POST or None, request.FILES or None, instance=resource, supervisor=request.user)
    if request.method == "POST" and form.is_valid():
        resource, targets = _save_shared_resource(form, request.user)
        notify_supervisees(
            author=request.user,
            projects=targets,
            title=f"Shared resource updated: {resource.title}",
            body="Your supervisor updated a shared file or guide. Open Notices and resources to view the latest version.",
        )
        log_event(actor=request.user, action="resource.updated", summary=f"Shared resource updated: {resource.title}", obj=resource)
        messages.success(request, "Resource updated and students were notified.")
        return redirect("announcements")
    return render(request, "supervision/resource_edit.html", {"form": form, "resource": resource})


@login_required
def download_shared_resource(request, resource_id):
    resource = get_object_or_404(SharedResource.objects.select_related("project", "department"), pk=resource_id)
    if not resource.file:
        raise Http404
    if request.user.role == Role.STUDENT:
        profile = getattr(request.user, "student_profile", None)
        if not profile or profile.student_status == StudentProfile.Status.GRADUATED:
            raise PermissionDenied
        can_access = SharedResource.objects.filter(student_resource_scope(request.user), pk=resource.pk).exists()
    elif request.user.role in (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD):
        can_access = resource.author_id == request.user.pk or resource.department_id == request.user.department_id
    else:
        # Administrators manage accounts and setup, not supervision material (D-14).
        can_access = False
    if not can_access:
        raise PermissionDenied
    opened, missing = open_stored_file(request, resource.file, "file")
    if missing:
        return missing
    return FileResponse(opened, as_attachment=True, filename=Path(resource.file.name).name)


@role_required(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD)
def availability(request):
    slots = SupervisorAvailability.objects.filter(supervisor=request.user)
    slot_form = AvailabilityForm(request.POST or None)
    slot_form.instance.supervisor = request.user
    if request.method == "POST" and request.POST.get("action") == "save_slot":
        if slot_form.is_valid():
            slot = slot_form.save(commit=False)
            slot.supervisor = request.user
            slot.save()
            assigned_projects = Project.objects.filter(supervisor=request.user, archived=False).select_related("department")
            notify_supervisees(
                author=request.user,
                projects=assigned_projects,
                title="Supervisor availability updated",
                body=f"Your supervisor shared recurring availability: {slot.get_weekday_display()} {slot.start_time:%H:%M}–{slot.end_time:%H:%M}, {slot.venue or slot.get_mode_display()}. You can request a meeting in this window from your Supervision meetings page.",
            )
            log_event(actor=request.user, action="supervisor.availability_updated", summary="Supervisor availability slot added", obj=slot)
            messages.success(request, "Availability saved. Your current students were notified.")
            return redirect("supervisor_availability")
    return render(request, "supervision/availability.html", {"slots": slots, "slot_form": slot_form})


@role_required(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD)
def approval_policy(request):
    profile, _ = SupervisorProfile.objects.get_or_create(user=request.user)
    old_values = (profile.approval_method, profile.approval_criteria)
    form = ApprovalPolicyForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        profile = form.save()
        criteria_changed = old_values != (profile.approval_method, profile.approval_criteria)
        notices = []
        if criteria_changed:
            projects = Project.objects.filter(supervisor=request.user, archived=False)
            notices = notify_supervisees(
                author=request.user,
                projects=projects,
                title="Supervisor approval criteria updated",
                body="Your supervisor updated the evidence and expectations used to review a project proposal. Review the Project Workflow page for the current criteria.",
            )
        log_event(actor=request.user, action="supervisor.approval_policy_updated", summary="Supervisor updated approval criteria", obj=profile)
        message = "Your project approval criteria have been saved."
        if notices:
            message += " Your current students were notified."
        messages.success(request, message)
        return redirect("approval_policy")
    return render(request, "supervision/approval_policy.html", {"form": form})


@login_required
def notifications(request):
    """The signed-in user's own notifications ("Alerts"), newest first; mark one or all as read.

    They come from run_automation and from account events such as an approved registration.
    Only the user's own rows are ever listed or changed.
    """
    own = Notification.objects.filter(recipient=request.user)
    if request.method == "POST":
        unread = own.filter(read_at__isnull=True)
        if request.POST.get("action") == "read_all":
            unread.update(read_at=timezone.now())
        elif request.POST.get("action") == "read" and request.POST.get("notification_id", "").isdigit():
            unread.filter(pk=request.POST["notification_id"]).update(read_at=timezone.now())
        return redirect("notifications")
    return render(request, "supervision/notifications.html", {"notifications": own[:100]})
