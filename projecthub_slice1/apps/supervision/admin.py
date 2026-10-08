"""Admin screens for the supervision record."""

from django.contrib import admin

from .models import (
    Announcement,
    AnnouncementAcknowledgement,
    MeetingRecordEdit,
    Notification,
    SharedResource,
    SupervisionLogEntry,
    SupervisionMeeting,
)


class AnnouncementAcknowledgementInline(admin.TabularInline):
    model = AnnouncementAcknowledgement
    extra = 0
    readonly_fields = ("user", "seen_at", "acknowledged_at")

    def has_add_permission(self, request, obj=None):
        return False


class MeetingRecordEditInline(admin.TabularInline):
    model = MeetingRecordEdit
    extra = 0
    readonly_fields = ("edited_by", "edited_at", "changes", "note")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SupervisionMeeting)
class SupervisionMeetingAdmin(admin.ModelAdmin):
    list_display = ("project", "scheduled_for", "mode", "status", "venue")
    list_filter = ("status", "mode", "scheduled_for")
    search_fields = ("project__title", "venue", "agenda")
    date_hierarchy = "scheduled_for"
    inlines = (MeetingRecordEditInline,)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "audience_label", "is_pinned", "requires_acknowledgement", "created_at")
    list_filter = ("is_pinned", "requires_acknowledgement", "created_at")
    search_fields = ("title", "body", "project__title")
    inlines = (AnnouncementAcknowledgementInline,)

    @admin.display(description="Audience")
    def audience_label(self, obj):
        return obj.audience_label


@admin.register(SharedResource)
class SharedResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "audience_label", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "description")

    @admin.display(description="Audience")
    def audience_label(self, obj):
        return obj.audience_label


@admin.register(SupervisionLogEntry)
class SupervisionLogEntryAdmin(admin.ModelAdmin):
    list_display = ("project", "kind", "author", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("project__title", "body")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient", "kind", "title", "read_at")
    list_filter = ("kind", "created_at", "read_at")
    search_fields = ("title", "recipient__username", "object_id")
    readonly_fields = ("recipient", "kind", "object_type", "object_id", "title", "body", "url", "created_at")

    def has_add_permission(self, request):
        return False  # created by run_automation through notify(), not by hand
