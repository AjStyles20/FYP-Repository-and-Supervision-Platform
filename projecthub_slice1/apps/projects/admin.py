"""Admin screens for project records.

The admin must not bypass the workflow. On a project, the supervisor, stage, stage dates and
archived flag are read-only: they change only through the audited assignment and workflow pages.
A project cannot be deleted here, because its workflow records would go with it.
Workflow records (status events, assignments, approval decisions, approval forms and completions)
can be viewed here but not added, changed or deleted.
"""

from django.contrib import admin

from .models import (
    ArchivedProject,
    Project,
    ProjectApprovalDecision,
    ProjectApprovalForm,
    ProjectCompletion,
    ProjectDocument,
    ProjectMilestone,
    ProjectStatusEvent,
    ProjectSupervisorAssignment,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """View-only: no add, change or delete, so the record keeps what the workflow wrote."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ProjectMilestoneInline(admin.TabularInline):
    model = ProjectMilestone
    extra = 0


class ProjectDocumentInline(admin.TabularInline):
    model = ProjectDocument
    extra = 0
    fields = ("title", "document_type", "file", "visibility", "is_demo")


class ProjectStatusEventInline(admin.TabularInline):
    model = ProjectStatusEvent
    extra = 0
    readonly_fields = ("from_stage", "to_stage", "actor", "note", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "document_type", "visibility", "project", "archived_project", "is_demo", "uploaded_at")
    list_filter = ("visibility", "document_type", "is_demo")
    search_fields = ("title", "project__title", "archived_project__title")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "department", "programme", "stage", "supervisor", "archived")
    list_filter = ("department", "programme", "stage", "archived", "is_demo")
    search_fields = ("title", "keywords", "student__first_name", "student__last_name", "supervisor__first_name")
    readonly_fields = (
        "supervisor", "stage", "approval_date", "submission_date", "defence_date", "archived",
        "created_at", "updated_at",
    )
    inlines = (ProjectMilestoneInline, ProjectDocumentInline, ProjectStatusEventInline)

    def has_delete_permission(self, request, obj=None):
        # Deleting a project would take its status events, approvals and completion with it.
        # purge_demo removes demo projects through the ORM, which this does not affect.
        return False


@admin.register(ProjectSupervisorAssignment)
class ProjectSupervisorAssignmentAdmin(ReadOnlyAdmin):
    list_display = ("project", "supervisor", "assigned_at", "ended_at", "assigned_by")
    list_filter = ("supervisor", "assigned_at", "ended_at")
    search_fields = ("project__title", "supervisor__first_name", "supervisor__last_name")
    readonly_fields = ("project", "supervisor", "assigned_by", "assigned_at", "ended_at", "change_reason")


@admin.register(ProjectStatusEvent)
class ProjectStatusEventAdmin(ReadOnlyAdmin):
    list_display = ("project", "from_stage", "to_stage", "actor", "created_at")
    list_filter = ("to_stage", "created_at")
    search_fields = ("project__title",)
    readonly_fields = ("project", "from_stage", "to_stage", "actor", "note", "created_at")


@admin.register(ProjectApprovalDecision)
class ProjectApprovalDecisionAdmin(ReadOnlyAdmin):
    list_display = ("project", "step", "decision", "decided_by", "decided_on", "created_at")
    list_filter = ("step", "decision", "created_at")
    search_fields = ("project__title", "proposed_title")


@admin.register(ProjectApprovalForm)
class ProjectApprovalFormAdmin(ReadOnlyAdmin):
    list_display = ("project", "supervisor_decision", "supervisor_signed_on", "coordinator_logged_on")
    list_filter = ("supervisor_decision", "coordinator_logged_on")
    search_fields = ("project__title", "proposed_title")


@admin.register(ProjectCompletion)
class ProjectCompletionAdmin(ReadOnlyAdmin):
    list_display = ("project", "hod", "signed_on", "graduation_verified", "graduation_year")
    list_filter = ("graduation_verified", "signed_on")
    search_fields = ("project__title",)


@admin.register(ArchivedProject)
class ArchivedProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "programme", "year", "supervisor", "is_demo")
    list_filter = ("year", "department", "programme", "is_demo")
    search_fields = ("title", "keywords", "student__first_name", "student__last_name")
    filter_horizontal = ("previous_supervisors",)
