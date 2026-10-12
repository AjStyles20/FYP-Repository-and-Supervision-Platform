"""Readable audit log entries: labels for action codes, and change details as "Field: old → new".

Display only. The stored AuditEvent rows keep their action codes and JSON details unchanged.
"""

from django import template

from apps.accounts.models import Role
from apps.projects.models import ProjectStage

register = template.Library()

ACTION_LABELS = {
    "account.password_reset": "Password reset by an administrator",
    "account.password_set": "Temporary password replaced",
    "account.registration_approve": "Student registration approved",
    "account.registration_reject": "Student registration rejected",
    "account.staff_created": "Staff account created",
    "account.staff_deactivated": "Staff account deactivated",
    "account.staff_reactivated": "Staff account reactivated",
    "account.staff_updated": "Staff account updated",
    "account.student_created": "Student account created",
    "account.student_deactivated": "Student account deactivated",
    "account.student_reactivated": "Student account reactivated",
    "account.student_updated": "Student account updated",
    "meeting.record_edited": "Meeting record edited",
    "meeting.scheduled": "Meeting scheduled",
    "meeting.supervisor_confirmed": "Meeting record confirmed by supervisor",
    "notice.acknowledged": "Notice acknowledged",
    "notice.published": "Notice published",
    "project.approval_logged": "Approval form logged",
    "project.archived": "Project signed off and archived",
    "project.created": "Project record created",
    "project.document_uploaded": "Project file uploaded",
    "project.media_added": "Screenshot or video added",
    "project.media_removed": "Screenshot or video removed",
    "project.proposed": "Proposal submitted",
    "project.stage_changed": "Project stage changed",
    "project.supervisor_assigned": "Supervisor assigned",
    "project.supervisor_decision": "Supervisor decision recorded",
    "project.supervisor_edited": "Project details edited by supervisor",
    "project.supervisor_unassigned": "Supervisor removed",
    "convocation.exported": "Convocation list downloaded",
    "repository.csv_import": "Past projects imported from CSV",
    "resource.published": "Resource shared",
    "resource.updated": "Resource updated",
    "supervisor.approval_policy_updated": "Review criteria updated",
    "supervisor.availability_updated": "Availability updated",
}
for _kind in ("faculty", "department", "programme"):
    for _verb, _past in (("created", "added"), ("updated", "updated"), ("deleted", "deleted")):
        ACTION_LABELS[f"structure.{_kind}_{_verb}"] = f"{_kind.capitalize()} {_past}"

FIELD_LABELS = {
    "can_assign_supervisors": "Can assign supervisors",
    "degree_type": "Award",
    "duration_years": "Duration (years)",
    "first_name": "First name",
    "last_name": "Last name",
    "graduation_verified": "Graduation verified",
    "rejected_rows": "Rejected rows",
    "signed_on": "Signed on",
    "document_type": "File type",
    "supervisor_id": "Supervisor (account #)",
}

OBJECT_LABELS = {
    "accounts.User": "Account",
    "academics.Faculty": "Faculty",
    "academics.Department": "Department",
    "academics.Programme": "Programme",
    "projects.Project": "Project",
    "projects.ArchivedProject": "Archived project",
    "supervision.Announcement": "Notice",
    "supervision.SharedResource": "Resource",
    "supervision.SupervisionMeeting": "Meeting",
}

ROLE_LABELS = dict(Role.choices)
STAGE_LABELS = dict(ProjectStage.choices)


@register.filter
def audit_label(action):
    """'account.staff_updated' -> 'Staff account updated'; unknown codes are humanised."""
    if action in ACTION_LABELS:
        return ACTION_LABELS[action]
    return action.replace(".", " ").replace("_", " ").capitalize()


@register.filter
def audit_object(object_type):
    return OBJECT_LABELS.get(object_type, object_type)


def _field(name):
    return FIELD_LABELS.get(name, name.replace("_", " ").capitalize())


def _value(name, value):
    if value is None or value == "":
        return "(blank)"
    if isinstance(value, bool) or value in ("True", "False"):
        return "Yes" if value in (True, "True") else "No"
    if name == "role":
        return ROLE_LABELS.get(value, value)
    return str(value)


@register.filter
def audit_details(event):
    """The event's details as rows: {"label", "before", "after"} for a change, {"label", "value"} otherwise."""
    details = event.details
    if not isinstance(details, dict):
        return [{"label": "Details", "value": str(details)}] if details else []
    rows = []
    if event.action == "project.stage_changed":
        rows.append({"label": "Stage", "before": STAGE_LABELS.get(details.get("from"), "(new)"),
                     "after": STAGE_LABELS.get(details.get("to"), details.get("to"))})
        if details.get("note"):
            rows.append({"label": "Note", "value": details["note"]})
        return rows
    for name, value in details.items():
        if isinstance(value, dict) and set(value) <= {"from", "to"}:
            rows.append({"label": _field(name), "before": _value(name, value.get("from")), "after": _value(name, value.get("to"))})
        else:
            rows.append({"label": _field(name), "value": _value(name, value)})
    return rows
