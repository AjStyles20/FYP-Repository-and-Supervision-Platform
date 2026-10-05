from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role

from .models import Project, ProjectSupervisorAssignment


@transaction.atomic
def assign_project_supervisor(project_id, supervisor, assigned_by, change_reason=""):
    project = Project.objects.select_for_update().get(pk=project_id)
    if project.archived:
        raise ValidationError("Archived projects cannot be reassigned.")
    if (
        supervisor.role not in (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD)
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
    return project, assignment, True
