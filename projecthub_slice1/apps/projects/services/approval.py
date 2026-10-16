"""The final-year project approval form workflow.

The department's paper process, as three steps:

1. The student agrees a topic with a supervisor and puts it on the form.
2. The supervisor accepts, or accepts with changes, and signs.
3. The member of staff who keeps the register logs the approved form.

Only step 3 makes the topic formally approved, and each step writes a status event so the
project's history shows who did what and when.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.services import log_event
from apps.accounts.models import Role
from ..models import (
    ApprovalDecisionStep,
    ProjectApprovalDecision,
    ProjectApprovalForm,
    ProjectStage,
    SupervisorDecision,
)
from .assignment import coordinates
from .lifecycle import record_transition

APPROVING_DECISIONS = (SupervisorDecision.ACCEPTED, SupervisorDecision.ACCEPTED_WITH_CHANGES)


@transaction.atomic
def save_proposal_draft(project, *, proposed_title, problem_statement="", objectives="", methodology="",
                        tools_and_technologies="", literature_review="", research_gap="",
                        working_project_demonstration=""):
    """Keep unfinished work. A draft is not with the supervisor (no student date), so they cannot
    decide on it; a supervisor's earlier comments stay visible while the student revises."""
    if hasattr(project, "approval_form") and project.approval_form.is_logged:
        raise ValidationError("This topic has already been approved and logged; start a new record to change it.")
    if project.stage != ProjectStage.PROPOSED:
        raise ValidationError("A proposal can only be edited while the project is at the proposal stage.")
    form, _ = ProjectApprovalForm.objects.update_or_create(project=project, defaults={
        "proposed_title": proposed_title, "problem_statement": problem_statement, "objectives": objectives,
        "methodology": methodology, "tools_and_technologies": tools_and_technologies,
        "literature_review": literature_review, "research_gap": research_gap,
        "working_project_demonstration": working_project_demonstration,
        "student_name_on_form": project.student.get_full_name() or project.student.username,
        "student_signed_on": None,
    })
    if project.title != proposed_title:
        project.title = proposed_title
        project.save(update_fields=["title", "updated_at"])
    return form


@transaction.atomic
def submit_proposal(project, *, proposed_title, problem_statement, objectives, methodology,
                    tools_and_technologies, literature_review="", research_gap="",
                    working_project_demonstration="", student_name_on_form="", signed_on=None):
    """Step 1. Record the student's proposal and keep the project title in step with it.

    Submitting dates the form (today unless given), which puts it with the supervisor, who is alerted."""
    signed_on = signed_on or timezone.localdate()
    student_name_on_form = student_name_on_form or project.student.get_full_name() or project.student.username
    if hasattr(project, "approval_form") and project.approval_form.is_logged:
        raise ValidationError("This topic has already been approved and logged; start a new record to change it.")
    if project.stage != ProjectStage.PROPOSED:
        raise ValidationError("A proposal can only be edited while the project is at the proposal stage.")
    method = "topic_only"
    supervisor_profile = getattr(project.supervisor, "supervisor_profile", None) if project.supervisor_id else None
    if supervisor_profile:
        method = supervisor_profile.approval_method

    form, _ = ProjectApprovalForm.objects.update_or_create(
        project=project,
        defaults={
            "proposed_title": proposed_title,
            "problem_statement": problem_statement,
            "objectives": objectives,
            "methodology": methodology,
            "tools_and_technologies": tools_and_technologies,
            "literature_review": literature_review,
            "research_gap": research_gap,
            "working_project_demonstration": working_project_demonstration,
            "approval_method": method,
            "approval_criteria_snapshot": "",
            "student_name_on_form": student_name_on_form,
            "student_signed_on": signed_on,
            "supervisor_decision": SupervisorDecision.PENDING,
            "supervisor_comments": "",
            "supervisor_name_on_form": "",
            "supervisor_signed_on": None,
            "coordinator_logged_by": None,
            "coordinator_logged_on": None,
            "coordinator_notes": "",
        },
    )
    if project.title != proposed_title:
        project.title = proposed_title
        project.save(update_fields=["title", "updated_at"])
    log_event(actor=project.student, action="project.proposed", summary=f"Proposal submitted for {project.title}", obj=project)
    if project.supervisor_id:
        from apps.supervision.models import NotificationKind
        from apps.supervision.services import notify
        notify(project.supervisor, NotificationKind.PROPOSAL_SUBMITTED, form,
               title=f"Proposal to review: {project.title}",
               body=f"{project.student.get_full_name() or project.student.username} submitted their proposal for your decision.",
               url=reverse("project_workflow", args=[project.pk]))
    return form


@transaction.atomic
def record_supervisor_decision(project, *, supervisor, decision, comments, name_on_form, signed_on):
    """Step 2. The supervisor accepts, accepts with changes, or declines."""
    if supervisor.role not in (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD) or project.supervisor_id != supervisor.pk:
        raise ValidationError("Only the assigned supervisor can decide on this proposal.")
    if project.stage != ProjectStage.PROPOSED:
        raise ValidationError("The supervisor decision has already been recorded.")
    form = _open_form(project)
    if not form.student_signed_on:
        raise ValidationError("The student has not submitted the proposal yet; it is still a draft.")
    if form.is_supervisor_signed:
        raise ValidationError("The student must update and resubmit the proposal before another decision.")
    profile = getattr(supervisor, "supervisor_profile", None)
    effective_method = profile.approval_method if profile else form.approval_method
    if effective_method == "literature_review" and (not form.literature_review.strip() or not form.research_gap.strip()):
        raise ValidationError("This supervisor requires a literature review and research gap before deciding.")
    if effective_method == "working_project" and not form.working_project_demonstration.strip():
        raise ValidationError("This supervisor requires working project or demonstration evidence before deciding.")
    if profile:
        form.approval_method = effective_method
        form.approval_criteria_snapshot = profile.approval_criteria
    form.supervisor_decision = decision
    form.supervisor_comments = comments
    form.supervisor_name_on_form = name_on_form
    form.supervisor_signed_on = signed_on
    form.save(update_fields=[
        "supervisor_decision",
        "approval_method",
        "approval_criteria_snapshot",
        "supervisor_comments",
        "supervisor_name_on_form",
        "supervisor_signed_on",
        "updated_at",
    ])
    _record_decision(form, ApprovalDecisionStep.SUPERVISOR, supervisor, decision=decision,
                     name_on_form=name_on_form, decided_on=signed_on, comments=comments)
    log_event(actor=supervisor, action="project.supervisor_decision", summary=f"Supervisor decision recorded for {project.title}", obj=project, details={"decision": decision})

    if decision in APPROVING_DECISIONS and project.stage == ProjectStage.PROPOSED:
        record_transition(
            project,
            ProjectStage.SUPERVISOR_ACCEPTED,
            actor=supervisor,
            note=f"Supervisor signed the approval form: {form.get_supervisor_decision_display()}.",
        )
    return form


@transaction.atomic
def log_approved_form(project, *, coordinator, notes, logged_on):
    """Step 3. The department logs the signed form, which is what makes the topic approved."""
    if not coordinates(coordinator, project.department_id):
        raise ValidationError("Only a coordinator of the project's faculty can log the approval form.")
    form = _open_form(project)
    if not form.is_supervisor_signed:
        raise ValidationError("The supervisor has not signed this form yet.")
    if project.stage_position < 2:  # ProjectStage.SUPERVISOR_ACCEPTED
        raise ValidationError("The supervisor's acceptance has not been recorded yet.")

    form.coordinator_logged_by = coordinator
    form.coordinator_logged_on = logged_on
    form.coordinator_notes = notes
    form.save(update_fields=["coordinator_logged_by", "coordinator_logged_on", "coordinator_notes", "updated_at"])
    _record_decision(form, ApprovalDecisionStep.COORDINATOR_LOG, coordinator,
                     name_on_form=coordinator.get_full_name() or coordinator.username,
                     decided_on=logged_on, comments=notes)
    log_event(actor=coordinator, action="project.approval_logged", summary=f"Approval form logged for {project.title}", obj=project)

    if not project.is_approved:
        record_transition(
            project,
            ProjectStage.APPROVED,
            actor=coordinator,
            note=f"Approved form logged by {coordinator.get_full_name() or coordinator.username}.",
            when=logged_on,
        )
    return form


def _record_decision(form, step, user, *, decision="", name_on_form="", decided_on=None, comments=""):
    """Append a permanent copy of this decision; the form itself is reset if the student resubmits."""
    return ProjectApprovalDecision.objects.create(
        project=form.project,
        step=step,
        decision=decision,
        decided_by=user,
        name_on_form=name_on_form,
        decided_on=decided_on,
        proposed_title=form.proposed_title,
        approval_method=form.approval_method,
        approval_criteria_snapshot=form.approval_criteria_snapshot,
        comments=comments,
    )


def _open_form(project):
    try:
        return project.approval_form
    except ProjectApprovalForm.DoesNotExist as error:
        raise ValidationError("No approval form has been started for this project.") from error
