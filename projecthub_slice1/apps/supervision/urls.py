from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:project_id>/meetings/", views.project_meetings, name="project_meetings"),
    path("meetings/<int:meeting_id>/", views.meeting_detail, name="meeting_detail"),
    path("meetings/<int:meeting_id>/edit/", views.edit_meeting, name="edit_meeting"),
    path("announcements/", views.announcements, name="announcements"),
    path("resources/<int:resource_id>/download/", views.download_shared_resource, name="download_shared_resource"),
    path("resources/<int:resource_id>/edit/", views.edit_shared_resource, name="edit_shared_resource"),
    path("availability/", views.availability, name="supervisor_availability"),
    path("approval-policy/", views.approval_policy, name="approval_policy"),
    path("projects/<int:project_id>/request-meeting/", views.request_meeting, name="request_meeting"),
]
