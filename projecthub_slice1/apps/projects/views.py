from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.academics.models import SEMESTER_CODE, normalise_semester_code
from apps.audit.services import log_event
from apps.accounts.models import Role, STAFF_ROLES, StudentProfile, User
from django.contrib.auth.decorators import login_required
from apps.accounts.permissions import role_required

from .forms import (
    AllocationForm, CompletionForm, CoordinatorApprovalForm, ProjectCsvImportForm, ProjectSemesterForm, ProjectDocumentForm, ProjectProposalForm, ProjectStartForm, StageActionForm,
    DeadlineForm, MilestoneForm, ProjectMediaForm, SupervisorAssignmentForm, SupervisorDecisionForm, SupervisorProjectEditForm, UnassignedSuperviseeForm,
)
from .models import (
    ArchivedProject, DocumentType, Project, ProjectApprovalForm, ProjectCompletion, ProjectDeadline, ProjectDocument, ProjectMedia, ProjectMilestone, ProjectStage,
    ProjectStatusEvent,
)
from .files import open_stored_file
from .imports import import_archived_projects
from .services.health import HEALTH_PREFETCH, can_see_health, health_score
from .services.similarity import similar_archived_projects, similarity_threshold
from .services.assignment import allocation_departments
from .services.milestones import apply_faculty_deadlines, create_deadline, remove_deadline, update_deadline
from .services.semesters import semester_for_code, set_archived_semester, set_project_semester
from .services import (
    save_proposal_draft, allocate_student, assign_project_supervisor, unassign_project_supervisor, log_approved_form, record_supervisor_decision,
    record_transition, sign_off_completion, submit_proposal, available_years,
    current_projects as repository_current_projects,
    faculties_with_structure, local_year, past_projects as repository_past_projects, read_filters,
)

REPOSITORY_ROLES = (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN, Role.STUDENT)
STUDENT_UPLOAD_STAGES = (ProjectStage.PROPOSED, ProjectStage.SUPERVISOR_ACCEPTED, ProjectStage.APPROVED, ProjectStage.IN_PROGRESS)
# The department's coordinator may upload the final document late in the project; the HOD still signs off.
COORDINATOR_UPLOAD_STAGES = (ProjectStage.IN_PROGRESS, ProjectStage.SUBMITTED, ProjectStage.DEFENDED)


def _coordinator_can_upload(user, project):
    return (
        user.role == Role.COORDINATOR and user.department_id is not None and user.department_id == project.department_id
        and not project.archived and project.stage in COORDINATOR_UPLOAD_STAGES
    )


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
        "semester": filters["semester"] or filters["semester_typed"],
        "semester_invalid": bool(filters["semester_typed"]) and not filters["semester"],
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
            "media": [item for item in project.media.all() if _can_open_current_project_files(request.user, item)],
            "similar_projects": similar_archived_projects(project.title, project.description),
            "similarity_threshold": similarity_threshold(),
        },
    )


def _can_set_semester(user, department_id):
    """The department's coordinator, or an administrator, chooses a project's semester (D-38)."""
    return user.role == Role.ADMIN or (
        user.role == Role.COORDINATOR and user.department_id is not None and user.department_id == department_id
    )


@role_required(*REPOSITORY_ROLES)
def past_project_detail(request, project_id):
    project = get_object_or_404(
        ArchivedProject.objects.select_related(
            "student", "student__student_profile", "department__faculty", "programme", "supervisor", "semester"
        ).prefetch_related("previous_supervisors"),
        pk=project_id,
    )
    can_set_semester = _can_set_semester(request.user, project.department_id)
    if request.method == "POST":
        if request.POST.get("action") != "set_semester" or not can_set_semester:
            raise PermissionDenied
        semester_form = ProjectSemesterForm(request.POST)
        if semester_form.is_valid():
            semester = semester_for_code(semester_form.cleaned_data["semester"], request.user)
            changed = set_archived_semester(project, semester, request.user)
            messages.success(request, f"Semester set to {project.semester or 'Not set'}." if changed else "Nothing changed.")
        else:
            messages.error(request, " ".join(semester_form.errors["semester"]))
        return redirect("past_project_detail", project_id=project.pk)
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
            # Older archive rows may list the final supervisor among the earlier ones; show each once.
            "previous_supervisors": [person for person in project.previous_supervisors.all() if person.pk != project.supervisor_id],
            "documents": project.documents.filter(visible_documents).select_related("uploaded_by"),
            "media": project.media.filter(visible_documents),
            "can_add_media": request.user.role == Role.ADMIN,
            "semester_form": ProjectSemesterForm(initial={"semester": project.semester.code if project.semester else ""}) if can_set_semester else None,
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
    opened, missing = open_stored_file(request, document.file, "file")
    if missing:
        return missing
    return FileResponse(opened, as_attachment=True, filename=Path(document.file.name).name)


def _save_media(request, form, *, project=None, archived_project=None):
    data = form.cleaned_data
    parent = project or archived_project
    item = ProjectMedia(
        project=project, archived_project=archived_project, kind=data["kind"], caption=data["caption"],
        video_url=data["video_url"] or "", visibility=data["visibility"], uploaded_by=request.user,
        is_demo=parent.is_demo,
    )
    if data["file"]:
        item.file = data["file"]
    item.save()
    log_event(actor=request.user, action="project.media_added", summary=f"{item.get_kind_display()} added to {parent.title}",
              obj=parent, details={"kind": item.kind, "caption": item.caption})
    return item


@role_required(Role.STUDENT)
def add_project_media(request, project_id):
    """The student adds a screenshot or a demo video to their running project (D-30)."""
    project = get_object_or_404(Project, pk=project_id, student=request.user, archived=False)
    form = ProjectMediaForm(request.POST or None, request.FILES or None, parent=project)
    if request.method == "POST" and form.is_valid():
        _save_media(request, form, project=project)
        messages.success(request, "Added. Your supervisor and department staff can see it; it joins the archive when the project is signed off.")
        return redirect("my_project")
    return render(request, "projects/media_upload.html", {"form": form, "parent": project, "back_url": reverse("my_project")})


@role_required(Role.ADMIN)
def add_archived_media(request, project_id):
    """An administrator adds a screenshot or a demo video to an archived project (D-30)."""
    project = get_object_or_404(ArchivedProject, pk=project_id)
    form = ProjectMediaForm(request.POST or None, request.FILES or None, parent=project)
    if request.method == "POST" and form.is_valid():
        _save_media(request, form, archived_project=project)
        messages.success(request, "Added to the archived project.")
        return redirect("past_project_detail", project_id=project.pk)
    return render(request, "projects/media_upload.html", {
        "form": form, "parent": project, "back_url": reverse("past_project_detail", args=[project.pk]),
    })


def _can_view_media(user, item):
    if item.project_id:
        return _can_open_current_project_files(user, item)
    if user.role in STAFF_ROLES or item.visibility == ProjectDocument.Visibility.BAZE_USERS:
        return True
    return item.archived_project.student_id == user.pk


@role_required(*REPOSITORY_ROLES)
def project_media_file(request, media_id):
    """Show an uploaded screenshot or play an uploaded video, after the same checks as project files."""
    item = get_object_or_404(ProjectMedia.objects.select_related("project", "archived_project"), pk=media_id)
    if not item.file or not _can_view_media(request.user, item):
        raise Http404  # 404, not 403, so an ID does not confirm the file exists
    opened, missing = open_stored_file(request, item.file, "image" if item.kind == ProjectMedia.Kind.IMAGE else "video")
    if missing:
        return missing
    response = FileResponse(opened, content_type=item.content_type)
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    return response


@require_POST
@role_required(Role.STUDENT, Role.ADMIN)
def remove_project_media(request, media_id):
    """The student removes media from their running project; an administrator from any project."""
    item = get_object_or_404(ProjectMedia.objects.select_related("project", "archived_project"), pk=media_id)
    is_owner = item.project_id and item.project.student_id == request.user.pk and not item.project.archived
    if request.user.role != Role.ADMIN and not is_owner:
        raise PermissionDenied
    parent = item.parent
    if item.file:
        stored = item.file
        transaction.on_commit(lambda: stored.delete(save=False))
    item.delete()
    log_event(actor=request.user, action="project.media_removed", summary=f"{item.get_kind_display()} removed from {parent.title}",
              obj=parent, details={"kind": item.kind, "caption": item.caption})
    messages.success(request, "Removed.")
    if item.archived_project_id:
        return redirect("past_project_detail", project_id=item.archived_project_id)
    return redirect("my_project" if is_owner else "current_project_detail", **({} if is_owner else {"project_id": item.project_id}))


@role_required(Role.COORDINATOR)
def faculty_deadlines(request):
    """The coordinator's common deadlines for every running project of their faculty (D-33)."""
    if not request.user.department_id:
        raise PermissionDenied
    faculty = request.user.department.faculty
    deadlines = ProjectDeadline.objects.filter(faculty=faculty).select_related("semester")
    action = request.POST.get("action", "") if request.method == "POST" else ""
    form = DeadlineForm(request.POST if action == "add" else None)
    if action == "add" and form.is_valid():
        semester = semester_for_code(form.cleaned_data["semester"], request.user)
        deadline = create_deadline(faculty, form.cleaned_data["name"], form.cleaned_data["due_date"], request.user, semester=semester)
        log_event(actor=request.user, action="deadline.created", summary=f"Deadline set: {deadline}", obj=deadline,
                  details={"semester": str(semester) if semester else "Every semester"})
        if semester:
            messages.success(request, f"{deadline.name} added to every running {semester} project of {faculty.name}.")
        else:
            messages.success(request, f"{deadline.name} added to every running project of {faculty.name}.")
        return redirect("faculty_deadlines")
    if action in ("update", "remove"):
        deadline = get_object_or_404(deadlines, pk=request.POST.get("deadline_id"))
        if action == "remove":
            log_event(actor=request.user, action="deadline.removed", summary=f"Deadline removed: {deadline}", obj=deadline)
            remove_deadline(deadline)
            messages.success(request, "Deadline removed. Milestones already done are kept.")
            return redirect("faculty_deadlines")
        edit_form = DeadlineForm(request.POST)
        if edit_form.is_valid():
            update_deadline(deadline, edit_form.cleaned_data["name"], edit_form.cleaned_data["due_date"])
            log_event(actor=request.user, action="deadline.updated", summary=f"Deadline changed: {deadline}", obj=deadline)
            messages.success(request, "Deadline updated on every project.")
        else:
            messages.error(request, "Give the deadline a name and a date.")
        return redirect("faculty_deadlines")
    return render(request, "projects/deadlines.html", {"faculty": faculty, "deadlines": deadlines, "form": form})


def _milestone_access(user, project):
    """(can_view, can_edit): the student and staff of the project's department read; its supervisor edits."""
    if project.supervisor_id == user.pk:
        return True, True
    if user.role == Role.STUDENT:
        return project.student_id == user.pk, False
    if user.role == Role.ADMIN:
        return True, False
    if user.role == Role.COORDINATOR and user.department_id:
        return project.department.faculty_id == user.department.faculty_id, False
    return user.role == Role.HOD and user.department_id == project.department_id, False


@login_required
def project_milestones(request, project_id):
    """Milestones and deadlines of one project: the faculty's deadlines plus the supervisor's own (D-33)."""
    project = get_object_or_404(Project.objects.select_related("student", "supervisor", "department"), pk=project_id, archived=False)
    can_view, can_edit = _milestone_access(request.user, project)
    if not can_view:
        raise PermissionDenied
    action = request.POST.get("action", "") if request.method == "POST" else ""
    if action and not can_edit:
        raise PermissionDenied
    form = MilestoneForm(request.POST if action == "add" else None)
    if action == "add" and form.is_valid():
        milestone = ProjectMilestone.objects.create(project=project, name=form.cleaned_data["name"],
                                                    due_date=form.cleaned_data["due_date"], position=project.milestones.count())
        log_event(actor=request.user, action="milestone.added", summary=f"Milestone added for {project.title}: {milestone.name}", obj=project)
        return redirect("project_milestones", project_id=project.pk)
    if action in ("toggle_done", "remove"):
        milestone = get_object_or_404(project.milestones, pk=request.POST.get("milestone_id"))
        if action == "remove":
            if milestone.deadline_id:
                raise PermissionDenied  # a faculty deadline is removed by the coordinator, not per project
            milestone.delete()
            log_event(actor=request.user, action="milestone.removed", summary=f"Milestone removed for {project.title}: {milestone.name}", obj=project)
        else:
            milestone.done = not milestone.done
            milestone.done_at = timezone.now() if milestone.done else None
            milestone.save(update_fields=["done", "done_at"])
            log_event(actor=request.user, action="milestone.done" if milestone.done else "milestone.reopened",
                      summary=f"Milestone {'done' if milestone.done else 'reopened'} for {project.title}: {milestone.name}", obj=project)
        return redirect("project_milestones", project_id=project.pk)
    return render(request, "projects/milestones.html", {
        "project": project, "milestones": project.milestones.select_related("deadline"), "form": form,
        "can_edit": can_edit, "today": timezone.localdate(),
    })


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
    media = project.media.all() if project else []
    return render(request, "projects/my_project.html", {"project": project, "documents": documents, "media": media})


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
        apply_faculty_deadlines(project)
        messages.success(request, "Project record created. Complete the proposal form to send it for review.")
        _warn_about_similar_topics(request, project)
        return redirect("project_workflow", project_id=project.pk)
    return render(request, "projects/project_start.html", {"form": form})


@role_required(*REPOSITORY_ROLES)
def project_workflow(request, project_id):
    """The role-checked action page for proposal, approval, lifecycle and HOD sign-off."""
    project = get_object_or_404(Project.objects.select_related("student", "supervisor", "semester"), pk=project_id)
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

    can_set_semester = not project.archived and _can_set_semester(user, project.department_id)
    if request.method == "POST" and request.POST.get("action") == "set_semester":
        if not can_set_semester:
            raise PermissionDenied
        semester_form = ProjectSemesterForm(request.POST)
        if semester_form.is_valid():
            semester = semester_for_code(semester_form.cleaned_data["semester"], user)
            changed = set_project_semester(project, semester, user)
            if changed:
                messages.success(request, f"Semester set to {project.semester or 'Not set'}. Its faculty deadlines now follow it.")
            else:
                messages.info(request, "Nothing changed.")
        else:
            messages.error(request, " ".join(semester_form.errors["semester"]))
        return redirect("project_workflow", project_id=project.pk)

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
            # The fields follow what the supervisor will check now; the form opens with what was saved.
            profile = getattr(project.supervisor, "supervisor_profile", None) if project.supervisor_id else None
            required_method = profile.approval_method if profile else "topic_only"
            saved = ProjectApprovalForm.objects.filter(project=project).first()
            initial = {name: getattr(saved, name) for name in ProjectProposalForm.base_fields} if saved else {"proposed_title": project.title}
            is_draft = action == "draft"
            form = ProjectProposalForm(request.POST or None, initial=initial, method=required_method, draft=is_draft)
            if request.method == "POST" and form.is_valid():
                if is_draft:
                    save_proposal_draft(project, **form.cleaned_data)
                    messages.success(request, "Draft saved. Your supervisor sees it only after you submit it.")
                else:
                    submit_proposal(project, **form.cleaned_data)
                    messages.success(request, "Proposal submitted. Your supervisor has been alerted. You can still edit it until they decide.")
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
    # Staff see the project's files here, each only if they could already open it; students use My project.
    documents = None
    if user.role in STAFF_ROLES:
        documents = [
            document
            for document in project.documents.select_related("project", "uploaded_by").order_by("-uploaded_at", "-pk")
            if _can_open_current_project_files(user, document)
        ]
    return render(request, "projects/workflow.html", {
        "documents": documents,
        "project": project,
        "form": form,
        "is_proposal_form": isinstance(form, ProjectProposalForm),
        "approval_method": approval_method,
        "approval_criteria": approval_criteria,
        "health": health_score(project) if can_see_health(user, project) else None,
        "show_similar": show_similar,
        "can_upload_final": _coordinator_can_upload(user, project),
        "semester_form": ProjectSemesterForm(initial={"semester": project.semester.code if project.semester else ""}) if can_set_semester else None,
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


CONVOCATION_COLUMNS = ("Student name", "Student ID", "Programme", "Project title", "Supervisor",
                       "Signed off on", "Graduation verified", "Graduation year", "Semester")


def _csv_safe(value):
    """Stop a spreadsheet treating a cell as a formula (CSV injection)."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


PROJECT_EXPORT_COLUMNS = ("Project title", "Student name", "Student ID", "Programme", "Department", "Supervisor",
                          "Stage", "Health", "Milestones done", "Overdue milestones", "Started on", "Semester")


@role_required(Role.COORDINATOR, Role.HOD, Role.ADMIN)
def export_projects(request):
    """The running projects in the viewer's scope as a CSV: a coordinator's faculty, an HOD's department,
    every project for an administrator. Health is filled only where the viewer may see it."""
    projects = Project.objects.filter(archived=False).select_related(
        "student__student_profile", "programme", "department", "supervisor", "semester"
    ).prefetch_related(*HEALTH_PREFETCH).order_by("department__name", "student__last_name", "student__first_name")
    if request.user.role == Role.COORDINATOR:
        projects = projects.filter(department__in=allocation_departments(request.user))
    elif request.user.role == Role.HOD:
        projects = projects.filter(department_id=request.user.department_id) if request.user.department_id else projects.none()
    today = timezone.localdate()
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="projects-{today:%Y-%m-%d}.csv"'
    response.write("\ufeff")  # lets Excel open the UTF-8 file with names intact
    import csv

    writer = csv.writer(response)
    writer.writerow(PROJECT_EXPORT_COLUMNS)
    count = 0
    for project in projects:
        profile = getattr(project.student, "student_profile", None)
        health = health_score(project) if can_see_health(request.user, project) else None
        milestones = list(project.milestones.all())
        writer.writerow([_csv_safe(value) for value in (
            project.title, project.student.get_full_name() or project.student.username,
            profile.student_number if profile else "", project.programme, project.department.name,
            project.supervisor.get_full_name() if project.supervisor else "Not assigned", project.get_stage_display(),
            f"{health.band_label} ({health.score})" if health else "",
            f"{sum(m.done for m in milestones)} of {len(milestones)}",
            sum(1 for m in milestones if not m.done and m.due_date and m.due_date < today),
            timezone.localtime(project.created_at).date().isoformat(),
            project.semester.code if project.semester else "Not set",
        )])
        count += 1
    log_event(actor=request.user, action="projects.exported", summary=f"Downloaded the project list ({count} projects)",
              details={"projects": count})
    return response


@role_required(Role.HOD)
def convocation_list(request):
    """Students whose project the HOD has signed off: the list the HOD used to write by hand."""
    completions = ProjectCompletion.objects.filter(
        project__department_id=request.user.department_id
    ).select_related(
        "project__student__student_profile", "project__programme", "project__supervisor", "project__semester"
    ).order_by("project__student__last_name", "project__student__first_name") if request.user.department_id else ProjectCompletion.objects.none()
    years = sorted({completion.signed_on.year for completion in completions}, reverse=True)
    year = request.GET.get("year", "")
    if year.isdigit():
        completions = completions.filter(signed_on__year=int(year))
    typed = normalise_semester_code(request.GET.get("semester", ""))
    semester = typed if SEMESTER_CODE.match(typed) else ""
    if semester:
        completions = completions.filter(project__semester__code=semester)
    rows = []
    for completion in completions:
        project = completion.project
        student = project.student
        profile = getattr(student, "student_profile", None)
        rows.append({
            "student_name": student.get_full_name() or student.username,
            "student_number": profile.student_number if profile else "",
            "programme": project.programme.award,
            "title": project.title,
            "supervisor": project.supervisor.get_full_name() if project.supervisor else "",
            "signed_on": completion.signed_on,
            "graduation_verified": completion.graduation_verified,
            "graduation_year": completion.graduation_year or "",
            "semester": project.semester.code if project.semester else "",
        })
    if request.GET.get("format") == "csv":
        import csv

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        label = year if year.isdigit() else "all-years"
        if semester:
            label += f"-{semester}"
        response["Content-Disposition"] = f'attachment; filename="convocation-list-{label}.csv"'
        response.write("\ufeff")  # lets Excel open the UTF-8 file with names intact
        writer = csv.writer(response)
        writer.writerow(CONVOCATION_COLUMNS)
        for row in rows:
            writer.writerow([_csv_safe(value) for value in (
                row["student_name"], row["student_number"], row["programme"], row["title"], row["supervisor"],
                row["signed_on"].isoformat(), "Yes" if row["graduation_verified"] else "No", row["graduation_year"],
                row["semester"] or "Not set",
            )])
        log_event(actor=request.user, action="convocation.exported", summary=f"Downloaded the convocation list ({label})",
                  details={"year": label, "students": len(rows)})
        return response
    return render(request, "projects/convocation.html", {"rows": rows, "years": years, "year": year, "semester": semester or typed,
                                                          "semester_invalid": bool(typed) and not semester,
                                                          "department": request.user.department})


@role_required(Role.COORDINATOR, Role.HOD, Role.ADMIN)
def approvals(request):
    # Coordinators log approved topics and record defences; the HOD only signs off (D-19).
    if request.user.role == Role.HOD:
        stages = [ProjectStage.DEFENDED]
    else:
        stages = [ProjectStage.PROPOSED, ProjectStage.SUPERVISOR_ACCEPTED, ProjectStage.SUBMITTED]
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
    # A coordinator allocates across their whole faculty; other allocators within their department (D-29).
    scope = allocation_departments(request.user)
    faculty_wide = request.user.role == Role.COORDINATOR
    projects = Project.objects.filter(archived=False, department__in=scope).select_related(
        "student", "department", "programme", "supervisor", "semester"
    ).prefetch_related("supervisor_assignments__supervisor", "supervisor_assignments__assigned_by")

    # Staff in scope with their current load; the least busy are listed first.
    workload_filter = Q(supervised_projects__archived=False) & Q(supervised_projects__department__in=scope)
    staff = User.objects.filter(
        is_active=True,
        role__in=(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD),
        department__in=scope,
    ).select_related("department").annotate(
        active_project_count=Count("supervised_projects", filter=workload_filter, distinct=True)
    ).order_by("active_project_count", "last_name", "first_name", "username")

    # Approved current students in scope who have no running project yet.
    waiting_students = User.objects.filter(
        role=Role.STUDENT, is_active=True,
        student_profile__registration_status=StudentProfile.RegistrationStatus.APPROVED,
        student_profile__student_status=StudentProfile.Status.CURRENT,
        student_profile__programme__department__in=scope,
    ).exclude(student_projects__archived=False).select_related("student_profile__programme").order_by(
        "last_name", "first_name", "username"
    )

    bound_form = None
    bound_project_id = None
    bound_student_id = None
    if request.method == "POST" and "student_id" in request.POST:
        raw_student_id = request.POST.get("student_id", "")
        if not raw_student_id.isdigit():
            raise Http404
        student = get_object_or_404(waiting_students, pk=raw_student_id)
        form = AllocationForm(request.POST, supervisor_queryset=staff)
        if form.is_valid():
            allocate_student(student, form.cleaned_data["supervisor"], request.user, form.cleaned_data["reason"],
                             faculty_wide=faculty_wide, semester=semester_for_code(form.cleaned_data["semester"], request.user))
            messages.success(request, f"{student.get_full_name() or student.username} is now supervised by "
                                      f"{form.cleaned_data['supervisor'].get_full_name() or form.cleaned_data['supervisor'].username}.")
            return redirect("supervisor_assignments")
        bound_form, bound_student_id = form, student.pk
    elif request.method == "POST":
        raw_project_id = request.POST.get("project_id", "")
        if not raw_project_id.isdigit():
            raise Http404
        project = get_object_or_404(projects, pk=raw_project_id)
        form = SupervisorAssignmentForm(
            request.POST,
            supervisor_queryset=staff if faculty_wide else staff.filter(department_id=project.department_id),
            current_supervisor=project.supervisor,
        )
        if form.is_valid():
            _, _, changed = assign_project_supervisor(
                project_id=project.pk,
                supervisor=form.cleaned_data["supervisor"],
                assigned_by=request.user,
                change_reason=form.cleaned_data["reason"],
                faculty_wide=faculty_wide,
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
        project_staff = staff if faculty_wide else staff.filter(department_id=project.department_id)
        form = (
            bound_form
            if project.pk == bound_project_id
            else SupervisorAssignmentForm(supervisor_queryset=project_staff, current_supervisor=project.supervisor)
        )
        rows.append({"project": project, "form": form})
    student_rows = [
        {"student": student, "form": bound_form if student.pk == bound_student_id else AllocationForm(supervisor_queryset=staff)}
        for student in waiting_students
    ]
    return render(
        request,
        "projects/supervisor_assignments.html",
        {"rows": rows, "student_rows": student_rows, "workloads": staff},
    )


# Documents the department's supervisors give every final-year student, offered on the Project guide.
# They live in department_documents/ (committed with the code) and are served only to signed-in
# users, unlike static files. Only names in this list can be downloaded.
DEPARTMENT_DOCUMENTS = (
    ("fyp-report-instructions.pdf", "FYP report instructions and template (PDF)",
     "Front pages, chapter structure, formatting, referencing (APA 7), plagiarism limits and hard-copy submission."),
    ("fyp-report-instructions.docx", "FYP report instructions and template (Word)",
     "The same document as a Word file, to write the report in."),
)


def _department_documents():
    documents = []
    for name, title, description in DEPARTMENT_DOCUMENTS:
        path = settings.BASE_DIR / "department_documents" / name
        documents.append({"name": name, "title": title, "description": description,
                          "size": path.stat().st_size if path.is_file() else None})
    return documents


@role_required(*REPOSITORY_ROLES)
def department_document(request, name):
    """Download one supervisor-provided document; any signed-in student or staff member."""
    if name not in {document_name for document_name, _, _ in DEPARTMENT_DOCUMENTS}:
        raise Http404
    try:
        handle = (settings.BASE_DIR / "department_documents" / name).open("rb")
    except OSError:
        return render(request, "file_missing.html", {"what": "file"}, status=404)
    return FileResponse(handle, as_attachment=True, filename=name)


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
    elif request.user.role == Role.ADMIN:
        # Shared guides are supervision material between supervisors and their students (D-14);
        # the administrator manages accounts and setup, so the page shows only the general guide.
        resources = SharedResource.objects.none()
    else:
        resources = SharedResource.objects.filter(
            Q(department_id=request.user.department_id) | Q(department__isnull=True)
        )
    resources = resources.select_related("author").distinct().order_by("-created_at")
    return render(request, "projects/guidelines.html", {
        "guide_resources": resources,
        "show_resources": request.user.role != Role.ADMIN,
        "department_documents": _department_documents(),
    })


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
            if row_errors:
                messages.error(request, "Nothing was imported. Correct the rows listed below and upload the whole file again.")
            else:
                messages.success(request, f"Imported {imported} archived project{'' if imported == 1 else 's'}.")
    return render(request, "projects/import_projects.html", {"form": form, "imported": imported, "row_errors": row_errors})


@role_required(Role.STUDENT, Role.COORDINATOR)
def upload_project_document(request, project_id):
    is_coordinator = request.user.role == Role.COORDINATOR
    if is_coordinator:
        # Only a project in the coordinator's own department; anything else is "not found".
        project = get_object_or_404(Project, pk=project_id, department_id=request.user.department_id or 0, archived=False)
        if not _coordinator_can_upload(request.user, project):
            raise PermissionDenied
    else:
        project = get_object_or_404(Project, pk=project_id, student=request.user, archived=False)
        if project.stage not in STUDENT_UPLOAD_STAGES:
            raise PermissionDenied
    initial = {"document_type": DocumentType.REPORT} if is_coordinator else None
    form = ProjectDocumentForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.project = project
        document.uploaded_by = request.user
        document.visibility = ProjectDocument.Visibility.STAFF_ONLY
        document.is_demo = project.is_demo
        document.save()
        log_event(actor=request.user, action="project.document_uploaded", summary=f"File uploaded for {project.title}", obj=project,
                  details={"document_type": document.document_type, "uploaded_by_role": request.user.role})
        if is_coordinator:
            messages.success(request, "File uploaded for the student. It moves into the archive when the HOD signs off.")
            return redirect("project_workflow", project_id=project.pk)
        messages.success(request, "File uploaded. It is visible to academic staff and to you.")
        return redirect("my_project")
    return render(request, "projects/document_upload.html", {"project": project, "form": form, "is_coordinator": is_coordinator})
