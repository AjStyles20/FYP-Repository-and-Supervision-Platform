"""D-19: the HOD appoints the FYP coordinator, signs off, and keeps the convocation list."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, SupervisorProfile, User
from apps.audit.models import AuditEvent

from .models import Project, ProjectCompletion, ProjectStage


class HodResponsibilitiesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Faculty of Computing and Applied Sciences")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        other = Department.objects.create(faculty=faculty, name="Software Engineering")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        other_programme = Programme.objects.create(department=other, name="Software Engineering", degree_type="BSc")
        cls.hod = User.objects.create(username="hod", first_name="Halima", role=Role.HOD, department=cls.department)
        cls.lecturer = User.objects.create(username="lecturer", first_name="Julius", last_name="Makinde",
                                           role=Role.SUPERVISOR, department=cls.department)
        SupervisorProfile.objects.create(user=cls.lecturer, title="Dr.")
        cls.outsider = User.objects.create(username="outsider", role=Role.SUPERVISOR, department=other)
        cls.other_hod = User.objects.create(username="other.hod", role=Role.HOD, department=cls.department)

        def project(student_name, number, stage, programme, supervisor=None):
            student = User.objects.create(username=student_name, first_name=student_name.title(), role=Role.STUDENT)
            StudentProfile.objects.create(user=student, student_number=number, programme=programme)
            return Project.objects.create(student=student, title=f"{student_name.title()} project", stage=stage,
                                          department=programme.department, programme=programme, supervisor=supervisor)

        cls.waiting_logging = project("amina", "BU/22/CS/1", ProjectStage.SUPERVISOR_ACCEPTED, cls.programme, cls.lecturer)
        cls.defended = project("ngozi", "BU/22/CS/2", ProjectStage.DEFENDED, cls.programme, cls.lecturer)
        signed_2025 = project("tunde", "BU/21/CS/3", ProjectStage.COMPLETED, cls.programme, cls.lecturer)
        signed_2026 = project("=cmd", "BU/22/CS/4", ProjectStage.COMPLETED, cls.programme, cls.lecturer)
        elsewhere = project("grace", "BU/21/SE/5", ProjectStage.COMPLETED, other_programme)
        ProjectCompletion.objects.create(project=signed_2025, hod=cls.hod, signed_on=date(2025, 7, 10),
                                         graduation_verified=True, graduation_year=2025)
        ProjectCompletion.objects.create(project=signed_2026, hod=cls.hod, signed_on=date(2026, 7, 1))
        ProjectCompletion.objects.create(project=elsewhere, hod=cls.hod, signed_on=date(2026, 7, 2))

    def setUp(self):
        self.client.force_login(self.hod)

    # --- department staff --------------------------------------------------------------------

    def test_only_the_hod_opens_department_staff(self):
        self.assertContains(self.client.get(reverse("department_staff")), "Julius Makinde")
        for user in (self.lecturer, User.objects.create(username="admin", role=Role.ADMIN)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("department_staff")).status_code, 403)

    def test_hod_appoints_and_removes_the_coordinator_with_an_audit_trail(self):
        page = self.client.get(reverse("department_staff"))
        self.assertContains(page, "No FYP coordinator yet")

        self.client.post(reverse("department_staff"), {"user_id": self.lecturer.pk, "action": "make_coordinator"})
        self.lecturer.refresh_from_db()
        self.assertEqual(self.lecturer.role, Role.COORDINATOR)
        self.assertNotContains(self.client.get(reverse("department_staff")), "No FYP coordinator yet")

        self.client.post(reverse("department_staff"), {"user_id": self.lecturer.pk, "action": "grant_allocation"})
        self.client.post(reverse("department_staff"), {"user_id": self.lecturer.pk, "action": "make_supervisor"})
        self.lecturer.refresh_from_db()
        self.assertEqual((self.lecturer.role, self.lecturer.can_assign_supervisors), (Role.SUPERVISOR, True))
        self.assertEqual(
            [event.details for event in AuditEvent.objects.filter(actor=self.hod).order_by("pk")],
            [{"role": {"from": "supervisor", "to": "coordinator"}},
             {"can_assign_supervisors": {"from": "False", "to": "True"}},
             {"role": {"from": "coordinator", "to": "supervisor"}}],
        )

    def test_hod_cannot_change_other_departments_hods_or_themselves(self):
        for target in (self.outsider, self.other_hod, self.hod):
            response = self.client.post(reverse("department_staff"), {"user_id": target.pk, "action": "make_coordinator"})
            self.assertEqual(response.status_code, 404, target.username)
        self.assertEqual(self.client.post(reverse("department_staff"), {"user_id": self.lecturer.pk, "action": "make_admin"}).status_code, 400)
        self.assertEqual(User.objects.filter(role=Role.COORDINATOR).count(), 0)

    def test_hod_still_cannot_do_the_coordinators_steps(self):
        response = self.client.post(reverse("project_workflow", args=[self.waiting_logging.pk]), {"notes": "x", "logged_on": "2026-10-09"})
        self.assertEqual(response.status_code, 403)

    # --- sign-off queue ----------------------------------------------------------------------

    def test_hod_queue_shows_only_projects_waiting_for_final_sign_off(self):
        response = self.client.get(reverse("approvals"))

        self.assertContains(response, "Final sign-off queue")
        self.assertContains(response, "Ngozi project")
        self.assertNotContains(response, "Amina project")

    # --- convocation list --------------------------------------------------------------------

    def test_convocation_list_shows_the_departments_signed_off_students(self):
        response = self.client.get(reverse("convocation_list"))

        self.assertContains(response, "2 students")
        self.assertContains(response, "BU/21/CS/3")
        self.assertContains(response, "Verified · 2025")
        self.assertNotContains(response, "Grace")
        self.assertContains(self.client.get(reverse("convocation_list"), {"year": "2025"}), "1 student signed off in 2025")

    def test_convocation_csv_download_is_safe_and_audited(self):
        response = self.client.get(reverse("convocation_list"), {"year": "2026", "format": "csv"})

        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="convocation-list-2026.csv"', response["Content-Disposition"])
        lines = response.content.decode("utf-8-sig").splitlines()
        self.assertEqual(lines[0], "Student name,Student ID,Programme,Project title,Supervisor,Signed off on,Graduation verified,Graduation year")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("'=Cmd,"), lines[1])  # a formula-like name cannot run in Excel
        self.assertEqual(AuditEvent.objects.get(action="convocation.exported").details, {"year": "2026", "students": 1})

    def test_only_the_hod_sees_the_convocation_list(self):
        self.client.force_login(self.lecturer)
        self.assertEqual(self.client.get(reverse("convocation_list")).status_code, 403)
