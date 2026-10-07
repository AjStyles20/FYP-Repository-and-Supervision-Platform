from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "summary")
    list_filter = ("action", "created_at")
    search_fields = ("summary", "object_type", "object_id", "actor__username")
    readonly_fields = ("actor", "action", "object_type", "object_id", "summary", "details", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
