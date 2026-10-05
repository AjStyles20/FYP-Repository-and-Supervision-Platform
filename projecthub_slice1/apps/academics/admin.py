from django.contrib import admin

from .models import Department, Faculty, Programme

admin.site.register(Faculty)
admin.site.register(Department)
admin.site.register(Programme)
