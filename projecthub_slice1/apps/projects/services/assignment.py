"""Assigning and reassigning a supervisor, with the audit trail kept intact.

Every call closes the previous assignment row and opens a new one. Nothing is ever overwritten,
so "who supervised this, from when to when, and who changed it" is always answerable.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.accounts.models import Role
from apps.academics.models import Department

from ..models import Project, ProjectStage, ProjectStatusEvent, ProjectSupervisorAssignment

# Title of a project record the coordinator creates when allocating a supervisor before the student
# has chosen a topic; the student's proposal replaces it (submit_proposal keeps the title in step).
TOPIC_TO_BE_AGREED = "Topic to be agreed"

SUPERVISOR_ROLES = (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD)


def can_supervise_in(user, department_id, *, require_active=True, faculty_wide=False):
    """The supervisor rule: academic staff (supervisor, coordinator or HOD) of the project's department,
    or of its faculty when a coordinator allocates (`faculty_wide`, D-29).

    The CSV importer passes require_active=False, because a historic project may name someone who
    has since left; assigning a running project always needs an active account.
    """
    if user.role not in SUPERVISOR_ROLES or not (user.is_active or not require_active):
        return False
    if user.department_id == department_id:
        return True
    return faculty_wide and Department.objects.filter(
        pk=department_id, faculty__departments__pk=user.department_id
    ).exists()


def allocation_departments(user):
    """The departments `user` allocates in (D-29): a coordinator works across their whole faculty,
    whatever their own teaching field; anyone else given the allocation permission (a supervisor or
    HOD), their own department."""
    if not user.department_id:
        return Department.objects.none()
    if user.role == Role.COORDINATOR:
        return Department.objects.filter(faculty_id=user.department.faculty_id)
    return Department.objects.filter(pk=user.department_id)


@transaction.atomic
def allocate_student(student, supervisor, assigned_by, change_reason="", *, faculty_wide=False):
    """The coordinator allocates a supervisor to a student who has no project yet.

    Creates the student's project record (stage Proposed, title "Topic to be agreed") and assigns
    the supervisor through assign_project_supervisor, so the history and audit are the same as for
    any other assignment. Returns the project.
    """
    profile = student.student_profile
    project = Project.objects.create(
        student=student, title=TOPIC_TO_BE_AGREED, programme=profile.programme,
        department=profile.programme.department, is_demo=student.is_demo,
    )
    ProjectStatusEvent.objects.create(
        project=project, from_stage="", to_stage=ProjectStage.PROPOSED, actor=assigned_by,
        note="Project record created by the coordinator when allocating a supervisor.",
    )
    log_event(actor=assigned_by, action="project.created", summary=f"Project record created for {student} at allocation", obj=project)
    from .milestones import apply_faculty_deadlines
    apply_faculty_deadlines(project)
    assign_project_supervisor(project.pk, supervisor, assigned_by, change_reason, faculty_wide=faculty_wide)
    return project


@transaction.atomic
def assign_project_supervisor(project_id, supervisor, assigned_by, change_reason="", *, faculty_wide=False):
    """Point `project_id` at `supervisor`, recording the change. Returns (project, assignment, changed)."""
    project = Project.objects.select_for_update().get(pk=project_id)
    if project.archived:
        raise ValidationError("Archived projects cannot be reassigned.")
    if not can_supervise_in(supervisor, project.department_id, faculty_wide=faculty_wide):
        raise ValidationError(
            f"Choose an active academic staff member from the project's {'faculty' if faculty_wide else 'department'}."
        )

    now = timezone.now()
    current_assignment = (
        ProjectSupervisorAssignment.objects.select_for_update()
        .filter(project=project, ended_at__isnull=True)
        .first()
    )
    if (
        current_assignment
        and current_assignment.supervisor_id == supervisor.pk
        and project.supervisor_id == supervisor.pk
    ):
        return project, current_assignment, False

    if current_assignment:
        current_assignment.ended_at = now
        current_assignment.save(update_fields=["ended_at"])
    elif project.supervisor_id and project.supervisor_id != supervisor.pk:
        # A supervisor was set before the audit trail existed; close a placeholder row so the
        # history still shows that somebody else once held this project.
        ProjectSupervisorAssignment.objects.create(
            project=project,
            supervisor_id=project.supervisor_id,
            assigned_at=project.created_at,
            ended_at=now,
            change_reason="Original assignment retained; assignment date and assigning staff were not recorded.",
        )

    project.supervisor = supervisor
    project.save(update_fields=["supervisor", "updated_at"])
    assignment = ProjectSupervisorAssignment.objects.create(
        project=project,
        supervisor=supervisor,
        assigned_by=assigned_by,
        assigned_at=now,
        change_reason=change_reason,
    )
    log_event(actor=assigned_by, action="project.supervisor_assigned", summary=f"{supervisor} assigned to {project.title}", obj=project, details={"supervisor_id": supervisor.pk, "reason": change_reason})
    return project, assignment, True


@transaction.atomic
def unassign_project_supervisor(project_id, *, supervisor, changed_by, change_reason=""):
    """Close a supervisor's current assignment without deleting the project or its history."""
    project = Project.objects.select_for_update().get(pk=project_id)
    if project.archived:
        raise ValidationError("Archived projects cannot be unassigned.")
    if project.supervisor_id != supervisor.pk:
        raise ValidationError("You can only remove a student from your own supervision roster.")
    now = timezone.now()
    assignment = (
        ProjectSupervisorAssignment.objects.select_for_update()
        .filter(project=project, supervisor=supervisor, ended_at__isnull=True)
        .first()
    )
    if assignment:
        assignment.ended_at = now
        if change_reason:
            assignment.change_reason = "\n".join(
                part for part in (assignment.change_reason, f"Unassigned: {change_reason}") if part
            )
        assignment.save(update_fields=["ended_at", "change_reason"])
    else:
        assignment = ProjectSupervisorAssignment.objects.create(
            project=project,
            supervisor=supervisor,
            assigned_by=changed_by,
            assigned_at=project.created_at,
            ended_at=now,
            change_reason=change_reason or "Supervisor assignment ended; original assignment time was not recorded.",
        )
    project.supervisor = None
    project.save(update_fields=["supervisor", "updated_at"])
    log_event(
        actor=changed_by,
        action="project.supervisor_unassigned",
        summary=f"{supervisor} removed from supervision of {project.title}",
        obj=project,
        details={"supervisor_id": supervisor.pk, "reason": change_reason},
    )
    return project, assignment, True


def supervision_history_for(project):
    """All assignment rows for a project, current first, with the current one first."""
    return project.supervisor_assignments.select_related("supervisor", "assigned_by").order_by("-assigned_at")


def previous_supervisors_for(project):
    """Everyone who supervised this project before the current supervisor."""
    return [
        row.supervisor
        for row in project.supervisor_assignments.filter(ended_at__isnull=False)
        .select_related("supervisor")
        .order_by("assigned_at")
    ]
