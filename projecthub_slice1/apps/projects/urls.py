from django.urls import path

from . import views

urlpatterns = [
    path("repository/", views.repository, name="repository"),
    path("repository/current/<int:project_id>/", views.current_project_detail, name="current_project_detail"),
    path("repository/past/<int:project_id>/", views.past_project_detail, name="past_project_detail"),
    path("documents/<int:document_id>/download/", views.download_project_document, name="download_project_document"),
    path("my-project/", views.my_project, name="my_project"),
    path("supervision/", views.supervision, name="supervision"),
    path("supervision/assignments/", views.supervisor_assignments, name="supervisor_assignments"),
    path("approvals/", views.approvals, name="approvals"),
    path("guidelines/", views.guidelines, name="guidelines"),
]
