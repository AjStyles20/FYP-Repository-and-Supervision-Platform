"""Delete every row flagged is_demo=True. Real (non-demo) data is never touched."""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import User
from apps.projects.models import ArchivedProject, Project


class Command(BaseCommand):
    help = "Remove all demo data (rows with is_demo=True)."

    @transaction.atomic
    def handle(self, *args, **opts):
        # Order matters: children first (profiles cascade with their users).
        counts = {}
        counts["archived_projects"] = ArchivedProject.objects.filter(is_demo=True).delete()[0]
        counts["projects"] = Project.objects.filter(is_demo=True).delete()[0]
        counts["users"] = User.objects.filter(is_demo=True).delete()[0]
        counts["programmes"] = Programme.objects.filter(is_demo=True).delete()[0]
        counts["departments"] = Department.objects.filter(is_demo=True).delete()[0]
        counts["faculties"] = Faculty.objects.filter(is_demo=True).delete()[0]
        self.stdout.write(self.style.SUCCESS(f"Removed demo rows: {counts}"))
