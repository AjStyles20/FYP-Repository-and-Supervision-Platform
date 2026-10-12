"""Faculty deadlines and the milestones they create on every running project (D-33)."""

from django.db import transaction

from ..models import Project, ProjectDeadline, ProjectMilestone


def apply_faculty_deadlines(project):
    """Give `project` a milestone for each of its faculty's deadlines it does not have yet."""
    have = set(project.milestones.exclude(deadline=None).values_list("deadline_id", flat=True))
    missing = ProjectDeadline.objects.filter(faculty_id=project.department.faculty_id).exclude(pk__in=have)
    ProjectMilestone.objects.bulk_create(
        ProjectMilestone(project=project, deadline=deadline, name=deadline.name, due_date=deadline.due_date,
                         position=deadline.position)
        for deadline in missing
    )


@transaction.atomic
def create_deadline(faculty, name, due_date, created_by):
    """A coordinator's new faculty deadline, added as a milestone to every running project of the faculty."""
    position = ProjectDeadline.objects.filter(faculty=faculty).count()
    deadline = ProjectDeadline.objects.create(faculty=faculty, name=name, due_date=due_date, position=position,
                                              created_by=created_by)
    projects = Project.objects.filter(archived=False, department__faculty=faculty)
    ProjectMilestone.objects.bulk_create(
        ProjectMilestone(project=project, deadline=deadline, name=name, due_date=due_date, position=position)
        for project in projects
    )
    return deadline


@transaction.atomic
def update_deadline(deadline, name, due_date):
    """A changed name or date reaches every milestone made from the deadline."""
    deadline.name, deadline.due_date = name, due_date
    deadline.save(update_fields=["name", "due_date"])
    deadline.milestones.update(name=name, due_date=due_date)


@transaction.atomic
def remove_deadline(deadline):
    """Milestones not yet done go with the deadline; done ones stay as a record (unlinked)."""
    deadline.milestones.filter(done=False).delete()
    deadline.delete()
