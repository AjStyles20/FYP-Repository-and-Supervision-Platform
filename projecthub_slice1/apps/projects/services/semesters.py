"""Semesters chosen by hand for each project (D-38), and the faculty deadlines that follow them."""

from django.db import transaction
from django.db.models import Q

from apps.audit.services import log_event

from ..models import ArchivedProject, ProjectDeadline


def deadlines_for(project):
    """The faculty deadlines that apply to `project`: those for every semester, plus its own semester's.

    A project whose semester is not set yet gets only the every-semester deadlines, so nobody
    receives another semester's dates by guesswork.
    """
    applies = Q(semester__isnull=True)
    if project.semester_id:
        applies |= Q(semester_id=project.semester_id)
    return ProjectDeadline.objects.filter(applies, faculty_id=project.department.faculty_id)


@transaction.atomic
def set_project_semester(project, semester, actor):
    """Put a running project in `semester` (or none) and bring its faculty-deadline milestones in line.

    Milestones from another semester's deadlines that are not done yet are removed; done ones stay
    as a record. Deadlines of the new semester are added. Returns True when something changed.
    """
    from .milestones import apply_faculty_deadlines

    if project.semester_id == (semester.pk if semester else None):
        return False
    before = str(project.semester) if project.semester_id else "Not set"
    project.semester = semester
    project.save(update_fields=["semester", "updated_at"])
    wrong = project.milestones.filter(done=False, deadline__semester__isnull=False)
    if semester:
        wrong = wrong.exclude(deadline__semester=semester)
    wrong.delete()
    apply_faculty_deadlines(project)
    log_event(actor=actor, action="project.semester_set", summary=f"Semester for {project.title}: {semester or 'Not set'}",
              obj=project, details={"semester": {"from": before, "to": str(semester) if semester else "Not set"}})
    return True


def set_archived_semester(archived, semester, actor):
    """Fill in or correct the semester on a past record (older records start with none)."""
    if archived.semester_id == (semester.pk if semester else None):
        return False
    before = str(archived.semester) if archived.semester_id else "Not set"
    ArchivedProject.objects.filter(pk=archived.pk).update(semester=semester)
    archived.semester = semester
    log_event(actor=actor, action="archive.semester_set", summary=f"Semester for past project {archived.title}: {semester or 'Not set'}",
              obj=archived, details={"semester": {"from": before, "to": str(semester) if semester else "Not set"}})
    return True
