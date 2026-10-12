"""The project list CSV: scope by role, safe cells, audited."""

import csv
from io import StringIO

from django.test import TestCase
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent

from .models import Project, ProjectStage
from .views import PROJECT_EXPORT_COLUMNS


class ProjectExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Computing")
        cs = Department.objects.create(faculty=faculty, name="Computer Science")
        cyber = Department.objects.create(faculty=faculty, name="Cyber Security")
        law = Department.objects.create(faculty=Faculty.objects.create(name="Law"), name="Private Law")
        cls.coordinator = User.objects.create(username="coord", role=Role.COORDINATOR, department=cyber)
        cls.hod = User.objects.create(username="hod", role=Role.HOD, department=cs)
        cls.admin = User.objects.create(username="admin.user", role=Role.ADMIN)
        cls.supervisor = User.objects.create(username="okoro", first_name="A.", last_name="Okoro", role=Role.SUPERVISOR, department=cs)

        def project(title, department, number):
            programme = Programme.objects.create(department=department, name=department.name, degree_type="BSc")
            student = User.objects.create(username=f"s{number}", first_name="Student", last_name=str(number), role=Role.STUDENT)
            StudentProfile.objects.create(user=student, student_number=f"BU/22A/XX/{number}", programme=programme)
            return Project.objects.create(student=student, title=title, stage=ProjectStage.IN_PROGRESS, department=department,
                                          programme=programme, supervisor=cls.supervisor if department == cs else None)

        project("=HYPERLINK(evil)", cs, 1001)
        project("Cyber topic", cyber, 1002)
        project("Law topic", law, 1003)

    def rows(self, user):
        self.client.force_login(user)
        response = self.client.get(reverse("export_projects"))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        return list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))

    def test_each_role_gets_its_own_scope(self):
        for user, titles in ((self.coordinator, {"'=HYPERLINK(evil)", "Cyber topic"}),
                             (self.hod, {"'=HYPERLINK(evil)"}),
                             (self.admin, {"'=HYPERLINK(evil)", "Cyber topic", "Law topic"})):
            with self.subTest(user.role):
                rows = self.rows(user)
                self.assertEqual(tuple(rows[0]), PROJECT_EXPORT_COLUMNS)
                self.assertEqual({row[0] for row in rows[1:]}, titles)

    def test_cells_cannot_become_formulas_and_the_download_is_audited(self):
        row = next(row for row in self.rows(self.admin)[1:] if "HYPERLINK" in row[0])
        self.assertEqual(row[0], "'=HYPERLINK(evil)")
        self.assertEqual((row[2], row[5], row[8]), ("BU/22A/XX/1001", "A. Okoro", "0 of 0"))
        self.assertEqual(AuditEvent.objects.get(action="projects.exported").details, {"projects": 3})

    def test_students_and_supervisors_cannot_download_it(self):
        student = User.objects.get(username="s1001")
        for user in (student, self.supervisor):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("export_projects")).status_code, 403)
