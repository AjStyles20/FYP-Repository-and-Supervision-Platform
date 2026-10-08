from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import Http404, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.audit.services import log_event
from apps.accounts.models import Role, STAFF_ROLES, StudentProfile, User
from apps.accounts.permissions import role_required

from .forms import (
    CompletionForm, CoordinatorApprovalForm, ProjectCsvImportForm, ProjectDocumentForm, ProjectProposalForm, ProjectStartForm, StageActionForm,
    SupervisorAssignmentForm, SupervisorDecisionForm, SupervisorProjectEditForm, UnassignedSuperviseeForm,
)
from .models import ArchivedProject, Project, ProjectDocument, ProjectStage, ProjectStatusEvent
from .imports import import_archived_projects
from .services.health import HEALTH_PREFETCH, can_see_health, health_score
from .services.similarity import similar_archived_projects, similarity_threshold
from .services import (
    assign_project_supervisor, unassign_project_supervisor, log_approved_form, record_supervisor_decision,
    record_transition, sign_off_completion, submit_proposal, available_years,
    current_projects as repository_current_projects,
    faculties_with_structure, local_year, past_projects as repository_past_projects, read_filters,
)

REPOSITORY_ROLES = (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN, Role.STUDENT)


def _warn_about_similar_topics(request, project):
    """After a student submits a topic: a warning only. The submission has already been saved."""
    matches = similar_archived_projects(project.title, project.description)
    if matches:
        messages.warning(
            request,
            f"{len(matches)} archived project{'' if len(matches) == 1 else 's'} look{'s' if len(matches) == 1 else ''} similar "
            "to your topic. Your topic was saved; read them below and discuss any overlap with your supervisor.",
        )


def _repository_context(request, section):
    can_see_student_id = request.user.role in STAFF_ROLES
    filters = read_filters(request.GET)
    query = filters["q"]
    current_projects = repository_current_projects(filters, can_see_student_id)
    past_projects = repository_past_projects(filters, can_see_student_id)

    if section == "current":
        items = current_projects
    elif section == "past":
        items = past_projects
    else:
        items = [(project, False) for project in current_projects]
        items.extend((project, True) for project in past_projects)
        items.sort(key=lambda row: (local_year(row[0].updated_at) if not row[1] else row[0].year, row[0].title.lower()), reverse=True)

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
                "year": project.year if is_past else local_year(project.updated_at),
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
        "faculty_id": filters["faculty"],
        "department_id": filters["department"],
        "programme_id": filters["programme"],
        "year": filters["year"],
        "years": available_years(),
        "faculties": faculties_with_structure(),
        "can_see_student_id": can_see_student_id,
        "section_count": {
            "current": current_projects.count(),
            "past": past_projects.count(),
        },
    }


@role_required(*REPOSITORY_ROLES)
def repository(request):
    if request.GET.get("section") == "current":
        query = request.GET.urlencode()
        return redirect(f"{reverse('running_topics')}?{query}" if query else "running_topics")
    context = _repository_context(request, "past")
    context["is_running_topics"] = False
    return render(request, "projects/repository.html", context)


@role_required(*REPOSITORY_ROLES)
def running_topics(request):
    context = _repository_context(request, "current")
    context["is_running_topics"] = True
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
            "similar_projects": similar_archived_projects(project.title, project.description),
            "similarity_threshold": similarity_threshold(),
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
    elif project.student_id == request.user.pk:
        visible_documents |= Q(uploaded_by=request.user)
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
            "similar_projects": similar_archived_projects(project.title, project.description, exclude_id=project.pk),
            "similarity_threshold": similarity_threshold(),
        },
    )


@role_required(*REPOSITORY_ROLES)
def download_project_document(request, document_id):
    document = get_object_or_404(ProjectDocument.objects.select_related("project"), pk=document_id)
    if document.project_id and not _can_open_current_project_files(request.user, document):
        # 404, not 403, so an ID from another department does not confirm the file exists.
        raise Http404
    if (
        document.visibility == ProjectDocument.Visibility.STAFF_ONLY
        and request.user.role not in STAFF_ROLES
        and document.uploaded_by_id != request.user.pk
    ):
        raise PermissionDenied
    return FileResponse(
        document.file.open("rb"),
        as_attachment=True,
        filename=Path(document.file.name).name,
    )


def _can_open_current_project_files(user, document):
    """Files of a project that is still running (archived files follow the repository rules).

    The project's student or the file's uploader; academic staff only within the project's
    department (or as its assigned supervisor); administrators for support.
    """
    project = document.project
    if user.pk in (project.student_id, document.uploaded_by_id):
        return True
    if user.role == Role.ADMIN:
        return True
    if user.role in (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD):
        return project.supervisor_id == user.pk or (
            user.department_id is not None and user.department_id == project.department_id
        )
    return False


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
        Project.objects.filter(student=request.user, archived=False)
        .select_related("student", "department", "programme", "supervisor")
        .prefetch_related("milestones", "meetings")
        .first()
    )
    documents = project.documents.filter(Q(visibility=ProjectDocument.Visibility.BAZE_USERS) | Q(uploaded_by=request.user)) if project else []
    return render(request, "projects/my_project.html", {"project": project, "documents": documents})


@role_required(Role.STUDENT)
def start_project(request):
    """Create the student's initial proposal record using their approved programme."""
    project = Project.objects.filter(student=request.user, archived=False).first()
    if project:
        return redirect("project_workflow", project_id=project.pk)
    try:
        profile = request.user.student_profile
    except StudentProfile.DoesNotExist:
        raise PermissionDenied
    if profile.registration_status != StudentProfile.RegistrationStatus.APPROVED:
        raise PermissionDenied
    form = ProjectStartForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = Project.objects.create(
            student=request.user,
            title=form.cleaned_data["title"],
            description=form.cleaned_data["description"],
            keywords=form.cleaned_data["keywords"],
            programme=profile.programme,
            department=profile.programme.department,
        )
        ProjectStatusEvent.objects.create(
            project=project, from_stage="", to_stage=ProjectStage.PROPOSED,
            actor=request.user, note="Student created the initial project record.",
        )
        log_event(actor=request.user, action="project.created", summary=f"Project record created: {project.title}", obj=project)
        messages.success(request, "Project record created. Complete the proposal form to send it for review.")
        _warn_about_similar_topics(request, project)
        return redirect("project_workflow", project_id=project.pk)
    return render(request, "projects/project_start.html", {"form": form})


@role_required(*REPOSITORY_ROLES)
def project_workflow(request, project_id):
    """The role-checked action page for proposal, approval, lifecycle and HOD sign-off."""
    project = get_object_or_404(Project.objects.select_related("student", "supervisor"), pk=project_id)
    user = request.user
    if user.role == Role.STUDENT:
        if project.student_id != user.pk:
            raise PermissionDenied
    elif user.role == Role.SUPERVISOR:
        if project.supervisor_id != user.pk:
            raise PermissionDenied
    elif user.role in (Role.COORDINATOR, Role.HOD):
        if project.department_id != user.department_id:
            raise PermissionDenied
    elif user.role != Role.ADMIN:
        raise PermissionDenied

    stage = project.stage
    approval_method = "topic_only"
    approval_criteria = ""
    if project.supervisor_id and getattr(project.supervisor, "supervisor_profile", None):
        approval_method = project.supervisor.supervisor_profile.approval_method
        approval_criteria = project.supervisor.supervisor_profile.approval_criteria
    if hasattr(project, "approval_form"):
        approval_method = project.approval_form.approval_method
        approval_criteria = project.approval_form.approval_criteria_snapshot or approval_criteria
    action = request.POST.get("action", "") if request.method == "POST" else ""
    form = None
    try:
        if user.role == Role.STUDENT and stage == ProjectStage.PROPOSED:
            form = ProjectProposalForm(request.POST or None)
            if request.method == "POST" and form.is_valid():
                submit_proposal(
                    project,
                    proposed_title=form.cleaned_data["proposed_title"],
                    problem_statement=form.cleaned_data["problem_statement"],
                    objectives=form.cleaned_data["objectives"],
                    methodology=form.cleaned_data["methodology"],
                    tools_and_technologies=form.cleaned_data["tools_and_technologies"],
                    student_name_on_form=user.get_full_name() or user.username,
                    signed_on=form.cleaned_data["signed_on"],
                )
                messages.success(request, "Proposal saved for your supervisor to review.")
                _warn_about_similar_topics(request, project)
                return redirect("project_workflow", project_id=project.pk)
        elif user.role in (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD) and project.supervisor_id == user.pk and stage == ProjectStage.PROPOSED:
            form = SupervisorDecisionForm(request.POST or None)
            if request.method == "POST" and form.is_valid():
                record_supervisor_decision(
                    project,
                    supervisor=user,
                    decision=form.cleaned_data["decision"],
                    comments=form.cleaned_data["comments"],
                    name_on_form=form.cleaned_data["name_on_form"],
                    signed_on=form.cleaned_data["signed_on"],
                )
                messages.success(request, "Your decision has been recorded.")
                return redirect("project_workflow", project_id=project.pk)
        elif user.role == Role.COORDINATOR and stage == ProjectStage.SUPERVISOR_ACCEPTED:
            form = CoordinatorApprovalForm(request.POST or None)
            if request.method == "POST" and form.is_valid():
                log_approved_form(project, coordinator=user, **form.cleaned_data)
                messages.success(request, "The signed approval form has been logged.")
                return redirect("project_workflow", project_id=project.pk)
        elif user.role in (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD) and project.supervisor_id == user.pk and stage == ProjectStage.APPROVED:
            form = StageActionForm(request.POST or None)
            if request.method == "POST" and form.is_valid():
                record_transition(project, ProjectStage.IN_PROGRESS, actor=user, note=form.cleaned_data["note"], when=form.cleaned_data["when"])
                messages.success(request, "Project marked as in progress.")
                return redirect("project_workflow", project_id=project.pk)
        elif user.role == Role.STUDENT and stage == ProjectStage.IN_PROGRESS:
            form = StageActionForm(request.POST or None)
            if request.method == "POST" and form.is_valid():
                record_transition(project, ProjectStage.SUBMITTED, actor=user, note=form.cleaned_data["note"], when=form.cleaned_data["when"])
                messages.success(request, "Project submission recorded.")
                return redirect("project_workflow", project_id=project.pk)
        elif user.role == Role.COORDINATOR and stage == ProjectStage.SUBMITTED:
            form = StageActionForm(request.POST or None)
            if request.method == "POST" and form.is_valid():
                record_transition(project, ProjectStage.DEFENDED, actor=user, note=form.cleaned_data["note"], when=form.cleaned_data["when"])
                messages.success(request, "Defence outcome recorded.")
                return redirect("project_workflow", project_id=project.pk)
        elif user.role == Role.HOD and stage == ProjectStage.DEFENDED:
            form = CompletionForm(request.POST or None, initial={"gap_summary": project.gap_summary})
            if request.method == "POST" and form.is_valid():
                sign_off_completion(project, user, **form.cleaned_data)
                messages.success(request, "Completion signed off and the project archived.")
                return redirect("past_project_detail", project_id=project.archive_record.pk)
        if request.method == "POST" and form is None:
            raise PermissionDenied
    except ValidationError as error:
        if form is not None:
            form.add_error(None, error.messages[0])
    show_similar = user.role == Role.STUDENT and stage == ProjectStage.PROPOSED
    return render(request, "projects/workflow.html", {
        "project": project,
        "form": form,
        "approval_method": approval_method,
        "approval_criteria": approval_criteria,
        "health": health_score(project) if can_see_health(user, project) else None,
        "show_similar": show_similar,
        "similar_projects": similar_archived_projects(project.title, project.description) if show_similar else [],
        "similarity_threshold": similarity_threshold(),
    })


@role_required(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN)
def supervision(request):
    current_projects = (
        Project.objects.filter(supervisor=request.user, archived=False)
        .select_related("student", "department", "programme", "supervisor")
        .prefetch_related(*HEALTH_PREFETCH)
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
    can_manage_roster = request.user.role == Role.SUPERVISOR
    unassigned_projects = Project.objects.none()
    add_form = None
    if can_manage_roster:
        if request.user.department_id:
            unassigned_projects = Project.objects.filter(
                department_id=request.user.department_id, supervisor__isnull=True, archived=False,
            ).select_related("student", "programme").order_by("student__last_name", "student__first_name")
        add_form = UnassignedSuperviseeForm(project_queryset=unassigned_projects)

    bound_project_id = None
    bound_edit_form = None
    if request.method == "POST":
        if not can_manage_roster:
            raise PermissionDenied
        action = request.POST.get("action")
        if action == "add_student":
            add_form = UnassignedSuperviseeForm(request.POST, project_queryset=unassigned_projects)
            if add_form.is_valid():
                project_to_add = add_form.cleaned_data["project"]
                assigned_project, _, _ = assign_project_supervisor(
                    project_id=project_to_add.pk,
                    supervisor=request.user,
                    assigned_by=request.user,
                    change_reason=add_form.cleaned_data["reason"],
                )
                from apps.supervision.services import notify_supervisees
                notify_supervisees(
                    author=request.user,
                    projects=[assigned_project],
                    title="You have a new supervisor",
                    body=f"{request.user.get_full_name() or request.user.username} is now supervising your project. Open your Student Portal for details.",
                )
                messages.success(request, f"{project_to_add.student_name} was added to your roster.")
                return redirect("supervision")
        elif action in {"remove_student", "edit_project"}:
            raw_id = request.POST.get("project_id", "")
            if not raw_id.isdigit():
                raise Http404
            project = get_object_or_404(Project, pk=raw_id, supervisor=request.user, archived=False)
            before = {field: getattr(project, field) for field in ("title", "description", "keywords")}
            if action == "remove_student":
                reason = request.POST.get("reason", "").strip()
                from apps.supervision.services import notify_supervisees
                notify_supervisees(
                    author=request.user,
                    projects=[project],
                    title="Supervisor assignment updated",
                    body="Your supervisor assignment has changed. Your project record and meeting history are retained by the department.",
                )
                project, _, _ = unassign_project_supervisor(
                    project.pk,
                    supervisor=request.user,
                    changed_by=request.user,
                    change_reason=reason,
                )
                messages.success(request, f"{project.student_name} was removed from your active roster. Their record was kept.")
                return redirect("supervision")
            bound_project_id = project.pk
            bound_edit_form = SupervisorProjectEditForm(request.POST, instance=project)
            if bound_edit_form.is_valid():
                updated = bound_edit_form.save()
                changed = {field: {"from": before[field], "to": getattr(updated, field)} for field in before if before[field] != getattr(updated, field)}
                if changed:
                    log_event(actor=request.user, action="project.supervisor_edited", summary=f"Supervisor updated project details: {updated.title}", obj=updated, details=changed)
                    from apps.supervision.services import notify_supervisees
                    notify_supervisees(
                        author=request.user,
                        projects=[updated],
                        title="Your project topic was updated",
                        body=f"Your supervisor updated your project details. The current title is: {updated.title}. The change is recorded at {updated.updated_at:%d %B %Y %H:%M}.",
                    )
                    messages.success(request, "Project details saved. The student was notified and the change was recorded.")
                else:
                    messages.info(request, "No project details changed.")
                return redirect("supervision")

    project_rows = []
    for project in current_projects:
        edit_form = (
            bound_edit_form
            if project.pk == bound_project_id
            else SupervisorProjectEditForm(instance=project)
        ) if can_manage_roster else None
        project_rows.append({"project": project, "edit_form": edit_form, "health": health_score(project)})
    return render(
        request,
        "projects/supervision.html",
        {
            "current_projects": current_projects,
            "project_rows": project_rows,
            "former_projects": former_projects,
            "archived_projects": archived_projects,
            "acting_sup": request.user.get_full_name() or request.user.username,
            "can_manage_roster": can_manage_roster,
            "add_form": add_form,
        },
    )


@role_required(Role.COORDINATOR, Role.HOD, Role.ADMIN)
def approvals(request):
    stages = [ProjectStage.PROPOSED, ProjectStage.SUPERVISOR_ACCEPTED, ProjectStage.SUBMITTED]
    if request.user.role == Role.HOD:
        stages.append(ProjectStage.DEFENDED)
    projects = Project.objects.filter(stage__in=stages, archived=False)
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
    from apps.supervision.models import SharedResource, student_resource_scope

    if request.user.role == Role.STUDENT:
        profile = getattr(request.user, "student_profile", None)
        if not profile or profile.student_status == StudentProfile.Status.GRADUATED:
            resources = SharedResource.objects.none()
        else:
            resources = SharedResource.objects.filter(student_resource_scope(request.user))
    elif request.user.role == Role.SUPERVISOR:
        resources = SharedResource.objects.filter(Q(author=request.user) | Q(projects__supervisor=request.user))
    else:
        resources = SharedResource.objects.filter(
            Q(department_id=request.user.department_id) | Q(department__isnull=True)
        ) if request.user.role != Role.ADMIN else SharedResource.objects.all()
    resources = resources.select_related("author").distinct().order_by("-created_at")
    return render(request, "projects/guidelines.html", {"guide_resources": resources})


@role_required(Role.ADMIN)
def import_projects(request):
    form = ProjectCsvImportForm(request.POST or None, request.FILES or None)
    imported = None
    row_errors = []
    if request.method == "POST" and form.is_valid():
        try:
            imported, row_errors = import_archived_projects(form.cleaned_data["file"])
        except ValidationError as error:
            form.add_error("file", error.messages[0])
        else:
            log_event(actor=request.user, action="repository.csv_import", summary=f"Imported {imported} archived project records", details={"imported": imported, "rejected_rows": len(row_errors)})
            messages.success(request, f"Imported {imported} archived project{'' if imported == 1 else 's'}.")
    return render(request, "projects/import_projects.html", {"form": form, "imported": imported, "row_errors": row_errors})


@role_required(Role.STUDENT)
def upload_project_document(request, project_id):
    project = get_object_or_404(Project, pk=project_id, student=request.user, archived=False)
    if project.stage not in (ProjectStage.PROPOSED, ProjectStage.SUPERVISOR_ACCEPTED, ProjectStage.APPROVED, ProjectStage.IN_PROGRESS):
        raise PermissionDenied
    form = ProjectDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.project = project
        document.uploaded_by = request.user
        document.visibility = ProjectDocument.Visibility.STAFF_ONLY
        document.is_demo = project.is_demo
        document.save()
        log_event(actor=request.user, action="project.document_uploaded", summary=f"File uploaded for {project.title}", obj=project, details={"document_type": document.document_type})
        messages.success(request, "File uploaded. It is visible to academic staff and to you.")
        return redirect("my_project")
    return render(request, "projects/document_upload.html", {"project": project, "form": form})
