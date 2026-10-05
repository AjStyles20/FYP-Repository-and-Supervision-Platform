from django.shortcuts import render

from apps.accounts.models import Role
from apps.accounts.permissions import role_required

from .models import Faculty


@role_required(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN)
def structure(request):
    """Read-only view of Faculty > Department > Programme. Staff roles only."""
    faculties = Faculty.objects.prefetch_related("departments__programmes").all()
    return render(request, "academics/structure.html", {"faculties": faculties})
