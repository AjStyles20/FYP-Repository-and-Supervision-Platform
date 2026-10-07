"""Assigning and reassigning a supervisor, with the audit trail kept intact.

Every call closes the previous assignment row and opens a new one. Nothing is ever overwritten,
so "who supervised this, from when to when, and who changed it" is always answerable.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.accounts.models import Role

from ..models import Project, ProjectSupervisorAssignment

SUPERVISOR_ROLES = (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD)


@transaction.atomic
def assign_project_supervisor(project_id, supervisor, assigned_by, change_reason=""):
    """Point `project_id` at `supervisor`, recording the change. Returns (project, assignment, changed)."""
    project = Project.objects.select_for_update().get(pk=project_id)
    if project.archived:
        raise ValidationError("Archived projects cannot be reassigned.")
    if (
        supervisor.role not in SUPERVISOR_ROLES
        or supervisor.department_id != project.department_id
        or not supervisor.is_active
    ):
        raise ValidationError("Choose an active academic staff member from the project's department.")

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
