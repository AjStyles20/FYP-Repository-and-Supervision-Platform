from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import Http404, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.accounts.models import Role, STAFF_ROLES, StudentProfile, User
from apps.accounts.permissions import role_required

from .forms import SupervisorAssignmentForm
from .models import ArchivedProject, Project, ProjectDocument, ProjectStage
from .services import assign_project_supervisor

REPOSITORY_ROLES = (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN, Role.STUDENT)


def _repository_context(request, section):
    query = request.GET.get("q", "").strip()
    faculty_id = request.GET.get("faculty", "")
    department_id = request.GET.get("department", "")
    programme_id = request.GET.get("programme", "")
    year = request.GET.get("year", "")
    can_see_student_id = request.user.role in STAFF_ROLES

    current_projects = (
        Project.objects.filter(archived=False)
        .select_related("student", "student__student_profile", "department__faculty", "programme", "supervisor")
        .order_by("-updated_at")
    )
    past_projects = (
        ArchivedProject.objects.select_related(
            "student", "student__student_profile", "department__faculty", "programme", "supervisor"
        )
        .prefetch_related("previous_supervisors")
        .order_by("-year", "-created_at")
    )

    for field, value in (
        ("department__faculty_id", faculty_id),
        ("department_id", department_id),
        ("programme_id", programme_id),
    ):
        if value.isdigit():
            current_projects = current_projects.filter(**{field: value})
            past_projects = past_projects.filter(**{field: value})

    if year.isdigit():
        current_projects = current_projects.filter(updated_at__year=year)
        past_projects = past_projects.filter(year=year)

    if query:
        current_search = (
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(supervisor__first_name__icontains=query)
            | Q(supervisor__last_name__icontains=query)
            | Q(department__name__icontains=query)
            | Q(programme__name__icontains=query)
        )
        past_search = (
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(gap_summary__icontains=query)
            | Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(supervisor__first_name__icontains=query)
            | Q(supervisor__last_name__icontains=query)
            | Q(department__name__icontains=query)
            | Q(programme__name__icontains=query)
        )
        if can_see_student_id:
            current_search |= Q(student__student_profile__student_number__icontains=query)
            past_search |= Q(student__student_profile__student_number__icontains=query)
        current_projects = current_projects.filter(current_search).distinct()
        past_projects = past_projects.filter(past_search).distinct()

    years = sorted(
        {date.year for date in Project.objects.filter(archived=False).dates("updated_at", "year", order="DESC")}
        | set(ArchivedProject.objects.values_list("year", flat=True)),
        reverse=True,
    )

    if section == "current":
        items = current_projects
    elif section == "past":
        items = past_projects
    else:
        items = [(project, False) for project in current_projects]
        items.extend((project, True) for project in past_projects)
        items.sort(key=lambda row: (row[0].updated_at.year if not row[1] else row[0].year, row[0].title.lower()), reverse=True)

    if section == "current":
        items = [(project, False) for project in items]
    elif section == "past":
        items = [(project, True) for project in items]

    item_cards = []
    for project, is_past in items:
        item_cards.append(
            {
                "project": project,
                "is_past": is_past,
                "year": project.year if is_past else project.updated_at.year,
                "stage": "" if is_past else project.get_stage_display(),
                "detail_url": reverse(
                    "past_project_detail" if is_past else "current_project_detail",
                    args=[project.pk],
                ),
            }
        )

    return {
        "items": item_cards,
        "section": section,
        "query": query,
        "faculty_id": faculty_id,
        "department_id": department_id,
        "programme_id": programme_id,
        "year": year,
        "years": years,
        "faculties": _academic_filters(),
        "can_see_student_id": can_see_student_id,
        "section_count": {
            "current": current_projects.count(),
            "past": past_projects.count(),
        },
    }


def _academic_filters():
    from apps.academics.models import Faculty

    return Faculty.objects.prefetch_related("departments__programmes").order_by("name")


@role_required(*REPOSITORY_ROLES)
def repository(request):
    section = request.GET.get("section", "current")
    if section not in {"current", "past", "all"}:
        section = "current"
    context = _repository_context(request, section)
    return render(request, "projects/repository.html", context)


@role_required(*REPOSITORY_ROLES)
def current_project_detail(request, project_id):
    project = get_object_or_404(
        Project.objects.select_related(
            "student", "student__student_profile", "department__faculty", "programme", "supervisor"
        ),
        pk=project_id,
        archived=False,
    )
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "is_past": False,
            "can_see_student_id": request.user.role in STAFF_ROLES,
            "student_profile": _student_profile(project.student),
            "previous_supervisors": [],
        },
    )


@role_required(*REPOSITORY_ROLES)
def past_project_detail(request, project_id):
    project = get_object_or_404(
        ArchivedProject.objects.select_related(
            "student", "student__student_profile", "department__faculty", "programme", "supervisor"
        ).prefetch_related("previous_supervisors"),
        pk=project_id,
    )
    visible_documents = Q(visibility=ProjectDocument.Visibility.BAZE_USERS)
    if request.user.role in STAFF_ROLES:
        visible_documents |= Q(visibility=ProjectDocument.Visibility.STAFF_ONLY)
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "is_past": True,
            "can_see_student_id": request.user.role in STAFF_ROLES,
            "student_profile": _student_profile(project.student),
            "previous_supervisors": list(project.previous_supervisors.all()),
            "documents": project.documents.filter(visible_documents),
        },
    )


@role_required(*REPOSITORY_ROLES)
def download_project_document(request, document_id):
    document = get_object_or_404(ProjectDocument, pk=document_id)
    if (
        document.visibility == ProjectDocument.Visibility.STAFF_ONLY
        and request.user.role not in STAFF_ROLES
    ):
        raise PermissionDenied
    return FileResponse(
        document.file.open("rb"),
        as_attachment=True,
        filename=Path(document.file.name).name,
    )


def _student_profile(student):
    try:
        return student.student_profile
    except StudentProfile.DoesNotExist:
        return None


@role_required(*REPOSITORY_ROLES)
def my_project(request):
    if request.user.role != Role.STUDENT:
        raise PermissionDenied
    project = (
        Project.objects.filter(student=request.user)
        .select_related("student", "department", "programme", "supervisor")
        .prefetch_related("milestones", "meeting_logs")
        .first()
    )
    return render(request, "projects/my_project.html", {"project": project})


@role_required(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN)
def supervision(request):
    current_projects = (
        Project.objects.filter(supervisor=request.user, archived=False)
        .select_related("student", "department", "programme", "supervisor")
        .order_by("-updated_at")
    )
    former_projects = (
        Project.objects.filter(
            supervisor_assignments__supervisor=request.user,
            supervisor_assignments__ended_at__isnull=False,
            archived=False,
        )
        .exclude(supervisor=request.user)
        .select_related("student", "department", "programme", "supervisor")
        .distinct()
        .order_by("-updated_at")
    )
    archived_projects = (
        ArchivedProject.objects.filter(Q(supervisor=request.user) | Q(previous_supervisors=request.user))
        .select_related("student", "department", "programme", "supervisor")
        .distinct()
        .order_by("-year", "-created_at")
    )
    return render(
        request,
        "projects/supervision.html",
        {
            "current_projects": current_projects,
            "former_projects": former_projects,
            "archived_projects": archived_projects,
            "acting_sup": request.user.get_full_name() or request.user.username,
        },
    )


@role_required(Role.COORDINATOR, Role.HOD, Role.ADMIN)
def approvals(request):
    projects = Project.objects.filter(
        stage__in=[ProjectStage.PROPOSED, ProjectStage.SUPERVISOR_ACCEPTED, ProjectStage.APPROVED]
    )
    if request.user.role != Role.ADMIN:
        if request.user.department_id:
            projects = projects.filter(department_id=request.user.department_id)
        else:
            projects = projects.none()
    projects = (
        projects
        .select_related("student", "supervisor", "department", "programme")
        .prefetch_related("milestones")
    )
    return render(request, "projects/approvals.html", {"projects": projects})


@role_required(*STAFF_ROLES)
def supervisor_assignments(request):
    if not request.user.can_assign_supervisors:
        raise PermissionDenied
    projects = Project.objects.filter(archived=False).select_related(
        "student", "department", "programme", "supervisor"
    ).prefetch_related("supervisor_assignments__supervisor", "supervisor_assignments__assigned_by")
    if not request.user.department_id:
        projects = projects.none()
    else:
        projects = projects.filter(department_id=request.user.department_id)

    staff = User.objects.filter(
        is_active=True,
        role__in=(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD),
    ).order_by("last_name", "first_name", "username")
    staff = staff.filter(department_id=request.user.department_id)

    bound_form = None
    bound_project_id = None
    if request.method == "POST":
        raw_project_id = request.POST.get("project_id", "")
        if not raw_project_id.isdigit():
            raise Http404
        project = get_object_or_404(projects, pk=raw_project_id)
        form = SupervisorAssignmentForm(
            request.POST,
            supervisor_queryset=staff.filter(department_id=project.department_id),
        )
        if form.is_valid():
            _, _, changed = assign_project_supervisor(
                project_id=project.pk,
                supervisor=form.cleaned_data["supervisor"],
                assigned_by=request.user,
                change_reason=form.cleaned_data["reason"],
            )
            if changed:
                messages.success(request, f"Supervisor assignment saved for {project.title}.")
            else:
                messages.info(request, f"{project.title} is already assigned to that supervisor.")
            return redirect("supervisor_assignments")
        bound_form = form
        bound_project_id = project.pk

    rows = []
    for project in projects:
        project_staff = staff.filter(department_id=project.department_id)
        form = (
            bound_form
            if project.pk == bound_project_id
            else SupervisorAssignmentForm(supervisor_queryset=project_staff)
        )
        rows.append({"project": project, "form": form})

    workload_filter = Q(supervised_projects__archived=False)
    workload_filter &= Q(supervised_projects__department_id=request.user.department_id)
    workloads = staff.annotate(
        active_project_count=Count(
            "supervised_projects",
            filter=workload_filter,
            distinct=True,
        )
    )
    return render(
        request,
        "projects/supervisor_assignments.html",
        {"rows": rows, "workloads": workloads},
    )


@role_required(*REPOSITORY_ROLES)
def guidelines(request):
    return render(request, "projects/guidelines.html")
