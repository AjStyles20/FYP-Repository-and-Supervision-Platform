from django.contrib import admin

from .models import Department, Faculty, Programme, Semester

admin.site.register(Faculty)
admin.site.register(Department)
admin.site.register(Programme)


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ("code", "starts_on", "ends_on", "is_demo")
