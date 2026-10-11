from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import StudentProfile, SupervisorProfile, User


@admin.register(User)
class ProjectHubUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Project Hub", {"fields": ("role", "department", "can_assign_supervisors", "must_change_password", "is_demo")}),
        ("Contact details", {"fields": ("personal_email", "personal_email_visibility", "phone", "phone_visibility")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Project Hub", {"fields": ("role", "department", "can_assign_supervisors")}),
    )
    list_display = ("username", "get_full_name", "role", "department", "can_assign_supervisors", "is_demo")
    list_filter = ("role", "is_demo")


admin.site.register(StudentProfile)
admin.site.register(SupervisorProfile)
