from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.ProjectLoginView.as_view(), name="login"),
    path("register/", views.register_student, name="register_student"),
    path("register/status/<str:token>/", views.registration_status, name="registration_status"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/summary/", views.api_summary, name="api_summary"),
    path("student/portal/", views.student_portal, name="student_portal"),
    path("alumni/portal/", views.alumni_portal, name="alumni_portal"),
    path("admin-tools/", views.admin_tools, name="admin_tools"),
    path("admin-tools/audit/", views.audit_log, name="audit_log"),
    path("admin-tools/staff/new/", views.add_staff_account, name="add_staff_account"),
    path("admin-tools/staff/<int:user_id>/", views.manage_staff_account, name="manage_staff_account"),
    path("admin-tools/students/<int:user_id>/", views.manage_student_account, name="manage_student_account"),
    path("students/new/", views.add_student_account, name="add_student_account"),
    path("account/password/", views.FirstPasswordChangeView.as_view(), name="password_change"),
    path("account/contact/", views.my_contact, name="my_contact"),
    path("department/staff/", views.department_staff, name="department_staff"),
    path(
        "admin-tools/registrations/<int:user_id>/review/",
        views.review_student_registration,
        name="review_student_registration",
    ),
]
