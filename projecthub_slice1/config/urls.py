from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("academics/", include("apps.academics.urls")),
    path("projects/", include("apps.projects.urls")),
    path("", include("apps.accounts.urls")),
]

handler403 = "apps.accounts.views.permission_denied_view"
