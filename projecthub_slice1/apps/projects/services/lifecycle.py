"""Project lifecycle: moving a stage forward, and the HOD sign-off that archives a project.

Two rules from the decision log shape everything here:

* D-15 — a defence and completion are different events. The HOD signs completion off after
  confirming the department's conditions; only then does the project become past work.
* Graduation is recorded only when the HOD confirms it. It is never inferred from the project
  finishing.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.accounts.models import Role, StudentProfile

from ..models import (
    ArchivedProject,
    DocumentType,
    Project,
    ProjectCompletion,
    ProjectStage,
    ProjectStatusEvent,
    STAGE_SEQUENCE,
)

# The stage at which each date becomes a fact.
STAGE_DATE_FIELD = {
    ProjectStage.APPROVED: "approval_date",
    ProjectStage.SUBMITTED: "submission_date",
    ProjectStage.DEFENDED: "defence_date",
}

TRANSITION_ROLES = {
    (ProjectStage.PROPOSED, ProjectStage.SUPERVISOR_ACCEPTED): (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD),
    (ProjectStage.SUPERVISOR_ACCEPTED, ProjectStage.APPROVED): (Role.COORDINATOR,),
    (ProjectStage.APPROVED, ProjectStage.IN_PROGRESS): (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD),
    (ProjectStage.IN_PROGRESS, ProjectStage.SUBMITTED): (Role.STUDENT,),
    (ProjectStage.SUBMITTED, ProjectStage.DEFENDED): (Role.COORDINATOR,),
}

# Steps taken in the capacity of the project's supervisor. Only the assigned supervisor may take
# these; the departmental steps (logging approval, recording the defence) belong to any
# coordinator in the project's department, whether or not they supervise it.
SUPERVISOR_TRANSITIONS = {
    (ProjectStage.PROPOSED, ProjectStage.SUPERVISOR_ACCEPTED),
    (ProjectStage.APPROVED, ProjectStage.IN_PROGRESS),
}


@transaction.atomic
def record_transition(project, to_stage, actor=None, note="", when=None):
    """Move a project to `to_stage`, stamp the matching date and append a status event."""
    if to_stage not in ProjectStage.values:
        raise ValidationError("That is not a valid project stage.")
    project = Project.objects.select_for_update().get(pk=project.pk)
    from_stage = project.stage
    allowed_roles = TRANSITION_ROLES.get((from_stage, to_stage))
    if not allowed_roles:
        raise ValidationError("That project stage transition is not allowed.")
    if actor is None or actor.role not in allowed_roles:
        raise ValidationError("Your role cannot record this project stage transition.")
    if (from_stage, to_stage) in SUPERVISOR_TRANSITIONS and project.supervisor_id != actor.pk:
        raise ValidationError("Only the assigned supervisor can record this transition.")
    if actor.role == Role.COORDINATOR and actor.department_id != project.department_id:
        raise ValidationError("Only a coordinator in the project's department can record this transition.")
    if actor.role == Role.HOD and actor.department_id != project.department_id:
        raise ValidationError("Only the HOD in the project's department can record this transition.")
    if actor.role == Role.STUDENT and project.student_id != actor.pk:
        raise ValidationError("You can only submit your own project.")
    if to_stage == ProjectStage.SUBMITTED and not project.documents.filter(document_type=DocumentType.REPORT).exists():
        raise ValidationError("Upload a final report before recording the submission.")
    update_fields = ["stage", "updated_at"]

    project.stage = to_stage
    date_field = STAGE_DATE_FIELD.get(to_stage)
    if date_field and when is not None:
        setattr(project, date_field, when)
        update_fields.append(date_field)

    project.save(update_fields=update_fields)
    event = ProjectStatusEvent.objects.create(
        project=project,
        from_stage=from_stage,
        to_stage=to_stage,
        actor=actor,
        note=note,
    )
    log_event(actor=actor, action="project.stage_changed", summary=f"{project.title}: {ProjectStage(to_stage).label}", obj=project, details={"from": from_stage, "to": to_stage, "note": note})
    return event


@transaction.atomic
def sign_off_completion(
    project,
    hod,
    signed_on,
    completion_note="",
    gap_summary="",
    graduation_verified=False,
    graduation_year=None,
    no_gap=False,
):
    """Record the HOD's completion sign-off and archive the project.

    The HOD must either record the documented gap or tick that there is none, so an empty gap on
    the archived record is always a deliberate statement, never an omission.

    Returns (completion, archived_project).
    """
    gap_summary = (gap_summary or "").strip()
    if gap_summary and no_gap:
        raise ValidationError("Either record the gap or confirm there is none, not both.")
    if not gap_summary and not no_gap:
        raise ValidationError("Record the documented gap, or confirm that there is none.")
    project = Project.objects.select_for_update().get(pk=project.pk)
    if project.archived:
        raise ValidationError("This project has already been signed off and archived.")
    if project.stage != ProjectStage.DEFENDED:
        raise ValidationError("A project can only be signed off after it has been defended.")
    if hod.role != Role.HOD or hod.department_id != project.department_id:
        raise ValidationError("Only the HOD for the project's department can sign off completion.")

    completion, _ = ProjectCompletion.objects.update_or_create(
        project=project,
        defaults={
            "hod": hod,
            "signed_on": signed_on or timezone.localdate(),
            "completion_note": completion_note,
            "gap_summary": gap_summary,
            "no_gap_confirmed": no_gap,
            "graduation_verified": graduation_verified,
            "graduation_year": graduation_year if graduation_verified else None,
        },
    )

    archived = _archive_project(project, completion)
    completion.archived_project = archived
    completion.save(update_fields=["archived_project"])
    log_event(actor=hod, action="project.archived", summary=f"{project.title} signed off and archived", obj=archived, details={"signed_on": str(completion.signed_on), "graduation_verified": graduation_verified})
    return completion, archived


def _archive_project(project, completion):
    """Create the past-work record, move the files across and update the student's status."""
    from .assignment import previous_supervisors_for

    archived = ArchivedProject.objects.create(
        title=project.title,
        description=project.description,
        keywords=project.keywords,
        year=completion.signed_on.year,
        completed_on=completion.signed_on,
        defence_date=project.defence_date,
        department=project.department,
        programme=project.programme,
        student=project.student,
        supervisor=project.supervisor,
        gap_summary=completion.gap_summary,
        continuation_link=project.continuation_link,
        archive_note=completion.completion_note,
        source_project=project,
        is_demo=project.is_demo,
    )
    archived.previous_supervisors.set(previous_supervisors_for(project))

    # Approved files belong to the archived record from now on.
    project.documents.update(archived_project=archived, project=None)
    project.media.update(archived_project=archived, project=None)

    project.archived = True
    project.stage = ProjectStage.COMPLETED
    project.save(update_fields=["archived", "stage", "updated_at"])

    _update_student_status(project, completion)
    ProjectStatusEvent.objects.create(
        project=project,
        from_stage=ProjectStage.DEFENDED,
        to_stage=ProjectStage.COMPLETED,
        actor=completion.hod,
        note=f"Completion signed off on {completion.signed_on:%d %b %Y} and archived as past work.",
    )
    return archived


def _update_student_status(project, completion):
    profile = getattr(project.student, "student_profile", None)
    if profile is None:
        return
    if completion.graduation_verified:
        profile.student_status = StudentProfile.Status.GRADUATED
        if completion.graduation_year:
            profile.graduation_year = completion.graduation_year
        profile.save(update_fields=["student_status", "graduation_year"])
    else:
        # The project is finished, but graduation has not been confirmed.
        profile.student_status = StudentProfile.Status.FYP_COMPLETED
        profile.save(update_fields=["student_status"])
