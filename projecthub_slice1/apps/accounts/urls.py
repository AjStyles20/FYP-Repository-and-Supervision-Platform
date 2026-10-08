from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.ProjectLoginView.as_view(), name="login"),
    path("register/", views.register_student, name="register_student"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/summary/", views.api_summary, name="api_summary"),
    path("student/portal/", views.student_portal, name="student_portal"),
    path("alumni/portal/", views.alumni_portal, name="alumni_portal"),
    path("admin-tools/", views.admin_tools, name="admin_tools"),
    path("admin-tools/audit/", views.audit_log, name="audit_log"),
    path(
        "admin-tools/registrations/<int:user_id>/review/",
        views.review_student_registration,
        name="review_student_registration",
    ),
]
