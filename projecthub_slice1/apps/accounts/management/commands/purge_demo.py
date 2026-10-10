"""Delete every row flagged is_demo=True. Real (non-demo) data is never touched."""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import User
from apps.projects.models import ArchivedProject, Project, ProjectDocument
from apps.supervision.models import SharedResource


class Command(BaseCommand):
    help = "Remove all demo data (rows with is_demo=True)."

    @transaction.atomic
    def handle(self, *args, **opts):
        # Order matters: children first (profiles cascade with their users).
        counts = {}
        # Demo files live on disk; deleting the rows alone would leave them behind. Remove them only
        # once the row deletes have committed, so a failed purge never loses files.
        demo_files = [document.file for document in ProjectDocument.objects.filter(is_demo=True).exclude(file="")]
        # Shared resources have no is_demo flag; they go with their demo author, and so do their files.
        demo_files += [resource.file for resource in SharedResource.objects.filter(author__is_demo=True).exclude(file="")]
        transaction.on_commit(lambda: [demo_file.delete(save=False) for demo_file in demo_files])
        counts["archived_projects"] = ArchivedProject.objects.filter(is_demo=True).delete()[0]
        counts["projects"] = Project.objects.filter(is_demo=True).delete()[0]
        counts["users"] = User.objects.filter(is_demo=True).delete()[0]
        counts["programmes"] = Programme.objects.filter(is_demo=True).delete()[0]
        counts["departments"] = Department.objects.filter(is_demo=True).delete()[0]
        counts["faculties"] = Faculty.objects.filter(is_demo=True).delete()[0]
        self.stdout.write(self.style.SUCCESS(f"Removed demo rows: {counts}"))
