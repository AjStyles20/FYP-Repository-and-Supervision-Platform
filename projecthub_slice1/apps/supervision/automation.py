"""The checks behind `python manage.py run_automation`.

Each check finds records that need a person's attention and calls notify() for each recipient.
notify() skips a (recipient, kind, object) that was already notified in the last 24 hours, so running
the checks again, by hand, from a scheduler or in --loop, creates nothing new until a day has passed.

  at_risk_project        health score above the at-risk band -> the supervisor and department coordinators
  pending_registration   student registration pending > 48 h  -> every active admin
  unacknowledged_notice  notice needing acknowledgement, > 48 h old -> each student in its audience who has not
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, StudentProfile, User
from apps.projects.models import Project, ProjectStage
from apps.projects.services.health import AT_RISK, HEALTH_PREFETCH, health_score

from .models import Announcement, AnnouncementAcknowledgement, NotificationKind
from .services import notify

logger = logging.getLogger("projecthub.automation")

DEFAULT_PENDING_REGISTRATION_HOURS = 48
DEFAULT_NOTICE_ACK_HOURS = 48


class Tally:
    """Per-kind counts for the run summary: records flagged, notifications created, duplicates skipped."""

    def __init__(self):
        self.flagged = self.created = self.skipped = 0

    def send(self, recipient, kind, obj, now, **message):
        if notify(recipient, kind, obj, now=now, **message):
            self.created += 1
        else:
            self.skipped += 1


def _hours(name, default):
    return timedelta(hours=getattr(settings, name, default))


def flag_at_risk_projects(now):
    tally = Tally()
    projects = (
        Project.objects.filter(archived=False).exclude(stage=ProjectStage.COMPLETED)
        .select_related("supervisor", "department").prefetch_related(*HEALTH_PREFETCH)
    )
    for project in projects:
        health = health_score(project, now=now)
        if health is None or health.band != AT_RISK:
            continue
        tally.flagged += 1
        recipients = {
            user.pk: user
            for user in User.objects.filter(role=Role.COORDINATOR, department_id=project.department_id, is_active=True)
        }
        if project.supervisor_id and project.supervisor.is_active:
            recipients[project.supervisor_id] = project.supervisor
        for recipient in recipients.values():
            tally.send(
                recipient, NotificationKind.AT_RISK_PROJECT, project, now,
                title=f"At risk ({health.score}/100): {project.title}",
                body="\n".join(health.reasons),
                url=reverse("project_workflow", args=[project.pk]),
            )
    return tally


def flag_pending_registrations(now):
    tally = Tally()
    cutoff = now - _hours("AUTOMATION_PENDING_REGISTRATION_HOURS", DEFAULT_PENDING_REGISTRATION_HOURS)
    # Same rows as the admin tools review list: real (non-demo) students still pending.
    waiting = User.objects.filter(
        role=Role.STUDENT, is_demo=False, date_joined__lte=cutoff,
        student_profile__registration_status=StudentProfile.RegistrationStatus.PENDING,
    ).order_by("date_joined")
    admins = list(User.objects.filter(role=Role.ADMIN, is_active=True))
    for student in waiting:
        tally.flagged += 1
        hours = int((now - student.date_joined).total_seconds() // 3600)
        for admin in admins:
            tally.send(
                admin, NotificationKind.PENDING_REGISTRATION, student, now,
                title=f"Registration waiting {hours} hours: {student.get_full_name() or student.username}",
                body=f"{student.email or student.username} registered on {timezone.localtime(student.date_joined):%d %b %Y %H:%M} and is still pending review.",
                url=reverse("admin_tools"),
            )
    return tally


def notice_audience(notice):
    """Current students who see this notice (same rules as the notices page), approved accounts only."""
    students = User.objects.filter(
        role=Role.STUDENT, is_active=True,
        student_profile__registration_status=StudentProfile.RegistrationStatus.APPROVED,
    ).exclude(student_profile__student_status=StudentProfile.Status.GRADUATED)
    if notice.project_id:
        students = students.filter(student_projects=notice.project_id)
    elif notice.department_id:
        students = students.filter(student_profile__programme__department_id=notice.department_id)
    return students.exclude(pk=notice.author_id).distinct()


def flag_unacknowledged_notices(now):
    tally = Tally()
    cutoff = now - _hours("AUTOMATION_NOTICE_ACK_HOURS", DEFAULT_NOTICE_ACK_HOURS)
    notices = Announcement.objects.filter(requires_acknowledgement=True, created_at__lte=cutoff).select_related("project")
    for notice in notices:
        acknowledged = AnnouncementAcknowledgement.objects.filter(
            announcement=notice, acknowledged_at__isnull=False
        ).values("user_id")
        missing = list(notice_audience(notice).exclude(pk__in=acknowledged))
        if missing:
            tally.flagged += 1
        for student in missing:
            tally.send(
                student, NotificationKind.UNACKNOWLEDGED_NOTICE, notice, now,
                title=f"Please acknowledge: {notice.title}",
                body="This notice asks you to confirm you have read it. Open Notices and press Acknowledge notice.",
                url=reverse("announcements"),
            )
    return tally


CHECKS = (
    (NotificationKind.AT_RISK_PROJECT, flag_at_risk_projects),
    (NotificationKind.PENDING_REGISTRATION, flag_pending_registrations),
    (NotificationKind.UNACKNOWLEDGED_NOTICE, flag_unacknowledged_notices),
)


def run_once(now=None):
    """Run every check once. Returns {kind: Tally} and logs a one-line summary."""
    now = now or timezone.now()
    results = {kind: check(now) for kind, check in CHECKS}
    logger.info(summary_line(results))
    return results


def summary_line(results):
    parts = [f"{kind}: {t.flagged} flagged, {t.created} new, {t.skipped} already sent" for kind, t in results.items()]
    total = sum(t.created for t in results.values())
    return f"run_automation: {total} new notification{'' if total == 1 else 's'} | " + " | ".join(parts)
