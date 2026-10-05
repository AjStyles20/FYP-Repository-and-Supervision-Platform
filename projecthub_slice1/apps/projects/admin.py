from django.contrib import admin

from .models import (
    ArchivedProject,
    Project,
    ProjectDocument,
    ProjectMeetingLog,
    ProjectMilestone,
    ProjectSupervisorAssignment,
)


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "visibility", "project", "archived_project", "is_demo", "uploaded_at")
    list_filter = ("visibility", "is_demo")
    search_fields = ("title", "project__title", "archived_project__title")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "department", "supervisor", "stage", "archived")
    list_filter = ("department", "stage", "archived")
    search_fields = ("title", "student__first_name", "student__last_name", "supervisor__first_name")
    readonly_fields = ("supervisor",)


admin.site.register(ArchivedProject)
admin.site.register(ProjectMilestone)
admin.site.register(ProjectMeetingLog)


@admin.register(ProjectSupervisorAssignment)
class ProjectSupervisorAssignmentAdmin(admin.ModelAdmin):
    list_display = ("project", "supervisor", "assigned_at", "ended_at", "assigned_by")
    list_filter = ("supervisor", "assigned_at", "ended_at")
    search_fields = ("project__title", "supervisor__first_name", "supervisor__last_name")
    readonly_fields = ("project", "supervisor", "assigned_by", "assigned_at", "ended_at", "change_reason")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
