"""Publishing notices to the active students who need to see them."""

from .models import Announcement


def notify_supervisees(*, author, projects, title, body):
    notices = []
    seen = set()
    for project in projects:
        if project.pk in seen or project.archived or project.supervisor_id != author.pk:
            continue
        seen.add(project.pk)
        notices.append(
            Announcement.objects.create(
                author=author,
                project=project,
                department=project.department,
                title=title,
                body=body,
            )
        )
    return notices
