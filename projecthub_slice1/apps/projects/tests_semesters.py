"""Semesters entered by hand (D-38): the labels, a project's semester, deadlines that follow it,
the archive keeping it, and the filters and lists that use it."""

import csv
from datetime import date
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme, Semester
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent

from .imports import CSV_COLUMNS, import_archived_projects
from .models import ArchivedProject, Project, ProjectCompletion, ProjectDeadline, ProjectMilestone, ProjectStage
from .services import sign_off_completion
from .services.milestones import apply_faculty_deadlines, create_deadline
from .services.semesters import set_project_semester


class SemesterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.faculty = Faculty.objects.create(name="Semester Faculty")
        cls.department = Department.objects.create(faculty=cls.faculty, name="Computer Science")
        cls.other = Department.objects.create(faculty=Faculty.objects.create(name="Other Faculty"), name="Law")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.coordinator = User.objects.create(username="sem.coord", role=Role.COORDINATOR, department=cls.department,
                                              can_assign_supervisors=True)
        cls.other_coordinator = User.objects.create(username="sem.other.coord", role=Role.COORDINATOR, department=cls.other)
        cls.supervisor = User.objects.create(username="sem.supervisor", role=Role.SUPERVISOR, department=cls.department)
        cls.hod = User.objects.create(username="sem.hod", role=Role.HOD, department=cls.department)
        cls.admin = User.objects.create(username="sem.admin", role=Role.ADMIN)
        cls.a = Semester.objects.create(code="26A")
        cls.b = Semester.objects.create(code="26B")

        def student(name):
            user = User.objects.create(username=f"sem.{name}", first_name=name.title(), role=Role.STUDENT)
            StudentProfile.objects.create(user=user, student_number=f"BU/22A/CS/{2000 + User.objects.count()}",
                                          programme=cls.programme)
            return user

        cls.student, cls.second, cls.waiting = student("ada"), student("bola"), student("chidi")
        cls.project = Project.objects.create(student=cls.student, title="Exam Planner", department=cls.department,
                                             programme=cls.programme, supervisor=cls.supervisor,
                                             stage=ProjectStage.IN_PROGRESS, semester=cls.a)
        cls.other_project = Project.objects.create(student=cls.second, title="Clinic Queue", department=cls.department,
                                                   programme=cls.programme, supervisor=cls.supervisor,
                                                   stage=ProjectStage.IN_PROGRESS, semester=cls.b)

    # --- the labels ------------------------------------------------------------------------------

    def test_codes_are_two_digits_and_a_b_or_c_and_stored_in_capitals(self):
        semester = Semester(code="26c")
        semester.full_clean()
        semester.save()
        self.assertEqual(Semester.objects.get(pk=semester.pk).code, "26C")
        for bad in ("26D", "2026A", "A26", "26"):
            with self.subTest(code=bad), self.assertRaises(ValidationError):
                Semester(code=bad).full_clean()
        with self.assertRaises(ValidationError):
            Semester(code="27A", starts_on=date(2027, 3, 1), ends_on=date(2027, 1, 1)).full_clean()

    def test_the_coordinator_and_the_admin_manage_semesters_and_others_cannot(self):
        url = reverse("semesters")
        for user in (self.coordinator, self.admin):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertContains(self.client.get(url), "26A")
        self.client.force_login(self.coordinator)
        response = self.client.post(url, {"action": "add", "new-code": "26c", "new-starts_on": "2026-09-01", "new-ends_on": ""})
        self.assertRedirects(response, url)
        self.assertTrue(Semester.objects.filter(code="26C", starts_on=date(2026, 9, 1)).exists())
        self.assertTrue(AuditEvent.objects.filter(action="semester.created").exists())
        # The same semester again, in lower case, is refused.
        page = self.client.post(url, {"action": "add", "new-code": "26a"})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(Semester.objects.filter(code="26A").count(), 1)
        # Dates can be noted later.
        prefix = f"s{self.b.pk}"
        self.client.post(url, {"action": "update", "semester_id": self.b.pk, f"{prefix}-code": "26B",
                               f"{prefix}-starts_on": "2026-05-04", f"{prefix}-ends_on": "2026-08-28"})
        self.b.refresh_from_db()
        self.assertEqual((self.b.starts_on, self.b.ends_on), (date(2026, 5, 4), date(2026, 8, 28)))
        for user in (self.supervisor, self.hod, self.student):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(url).status_code, 403)

    # --- deadlines follow the semester -----------------------------------------------------------

    def milestone_names(self, project):
        return set(project.milestones.values_list("name", flat=True))

    def test_a_semester_deadline_reaches_only_that_semesters_projects(self):
        create_deadline(self.faculty, "Chapter 3 (26A)", date(2026, 2, 15), self.coordinator, semester=self.a)
        create_deadline(self.faculty, "Ethics form", date(2026, 3, 1), self.coordinator)
        self.assertEqual(self.milestone_names(self.project), {"Chapter 3 (26A)", "Ethics form"})
        self.assertEqual(self.milestone_names(self.other_project), {"Ethics form"})
        unset = Project.objects.create(student=self.waiting, title="No semester yet", department=self.department,
                                       programme=self.programme)
        apply_faculty_deadlines(unset)
        self.assertEqual(self.milestone_names(unset), {"Ethics form"})  # never another semester's dates by guesswork

    def test_moving_a_project_to_another_semester_swaps_its_deadlines_and_keeps_done_ones(self):
        chapter_a = create_deadline(self.faculty, "Chapter 3 (26A)", date(2026, 2, 15), self.coordinator, semester=self.a)
        create_deadline(self.faculty, "Draft (26A)", date(2026, 3, 15), self.coordinator, semester=self.a)
        create_deadline(self.faculty, "Chapter 3 (26B)", date(2026, 6, 15), self.coordinator, semester=self.b)
        ProjectMilestone.objects.filter(project=self.project, deadline=chapter_a).update(done=True)

        self.assertTrue(set_project_semester(self.project, self.b, self.coordinator))

        self.assertEqual(self.milestone_names(self.project), {"Chapter 3 (26A)", "Chapter 3 (26B)"})  # done one kept
        self.assertFalse(set_project_semester(self.project, self.b, self.coordinator))  # no change, no event
        self.assertEqual(AuditEvent.objects.filter(action="project.semester_set").count(), 1)

    def test_the_departments_coordinator_sets_the_semester_on_the_workflow_page(self):
        url = reverse("project_workflow", args=[self.project.pk])
        create_deadline(self.faculty, "Chapter 3 (26B)", date(2026, 6, 15), self.coordinator, semester=self.b)
        self.client.force_login(self.coordinator)
        self.assertContains(self.client.get(url), "Save semester")
        self.assertRedirects(self.client.post(url, {"action": "set_semester", "semester": self.b.pk}), url,
                             fetch_redirect_response=False)
        self.project.refresh_from_db()
        self.assertEqual(self.project.semester, self.b)
        self.assertIn("Chapter 3 (26B)", self.milestone_names(self.project))
        for user in (self.supervisor, self.student, self.hod):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertNotContains(self.client.get(url), "Save semester")
                self.assertEqual(self.client.post(url, {"action": "set_semester", "semester": self.a.pk}).status_code, 403)
        self.project.refresh_from_db()
        self.assertEqual(self.project.semester, self.b)

    def test_allocation_can_choose_the_semester(self):
        create_deadline(self.faculty, "Chapter 1 (26B)", date(2026, 5, 20), self.coordinator, semester=self.b)
        self.client.force_login(self.coordinator)
        self.client.post(reverse("supervisor_assignments"), {"student_id": self.waiting.pk, "supervisor": self.supervisor.pk,
                                                              "reason": "", "semester": self.b.pk})
        project = Project.objects.get(student=self.waiting)
        self.assertEqual(project.semester, self.b)
        self.assertEqual(self.milestone_names(project), {"Chapter 1 (26B)"})

    # --- the archive keeps it, and lists use it --------------------------------------------------

    def test_sign_off_keeps_the_semester_even_in_the_next_calendar_year(self):
        Project.objects.filter(pk=self.project.pk).update(stage=ProjectStage.DEFENDED, semester=self.a)
        self.project.refresh_from_db()
        _, archived = sign_off_completion(self.project, self.hod, signed_on=date(2027, 1, 8), no_gap=True)
        self.assertEqual((archived.year, archived.semester), (2027, self.a))

    def test_older_past_records_get_their_semester_from_the_coordinator(self):
        archived = ArchivedProject.objects.create(title="Old record", year=2024, department=self.department,
                                                  programme=self.programme, student=self.student)
        url = reverse("past_project_detail", args=[archived.pk])
        self.client.force_login(self.supervisor)
        self.assertContains(self.client.get(url), "Semester not set")
        self.assertEqual(self.client.post(url, {"action": "set_semester", "semester": self.a.pk}).status_code, 403)
        self.client.force_login(self.other_coordinator)
        self.assertEqual(self.client.post(url, {"action": "set_semester", "semester": self.a.pk}).status_code, 403)
        self.client.force_login(self.coordinator)
        self.assertRedirects(self.client.post(url, {"action": "set_semester", "semester": self.a.pk}), url)
        archived.refresh_from_db()
        self.assertEqual(archived.semester, self.a)
        self.assertContains(self.client.get(url), "Semester 26A")

    def test_the_repository_filters_by_semester(self):
        ArchivedProject.objects.create(title="Past 26A", year=2026, semester=self.a, department=self.department,
                                       programme=self.programme, student=self.student)
        ArchivedProject.objects.create(title="Past 26B", year=2026, semester=self.b, department=self.department,
                                       programme=self.programme, student=self.second)
        self.client.force_login(self.supervisor)
        past = self.client.get(reverse("repository"), {"semester": self.a.pk})
        self.assertEqual([item["project"].title for item in past.context["items"]], ["Past 26A"])
        self.assertContains(past, '<option value="%d" selected>26A</option>' % self.a.pk, html=True)
        running = self.client.get(reverse("running_topics"), {"semester": self.b.pk})
        self.assertEqual([item["project"].title for item in running.context["items"]], ["Clinic Queue"])

    def test_the_convocation_list_and_the_export_show_the_semester(self):
        ProjectCompletion.objects.create(project=self.project, hod=self.hod, signed_on=date(2027, 1, 8))
        ProjectCompletion.objects.create(project=self.other_project, hod=self.hod, signed_on=date(2026, 9, 1))
        self.client.force_login(self.hod)
        page = self.client.get(reverse("convocation_list"), {"semester": self.a.pk})
        self.assertEqual([row["title"] for row in page.context["rows"]], ["Exam Planner"])
        rows = list(csv.reader(StringIO(self.client.get(reverse("convocation_list"), {"format": "csv"}).content.decode("utf-8-sig"))))
        self.assertEqual(rows[0][-1], "Semester")
        self.assertEqual(sorted(row[-1] for row in rows[1:]), ["26A", "26B"])

        self.client.force_login(self.coordinator)
        rows = list(csv.reader(StringIO(self.client.get(reverse("export_projects")).content.decode("utf-8-sig"))))
        self.assertEqual(rows[0][-1], "Semester")
        self.assertEqual(sorted(row[-1] for row in rows[1:]), ["26A", "26B"])

    def test_the_csv_import_takes_an_optional_semester_column(self):
        columns = (*CSV_COLUMNS, "semester")

        def upload(semester):
            out = StringIO()
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            writer.writerow({"title": f"Imported {semester or 'none'}", "year": "2025", "department": "Computer Science",
                             "programme": "Computer Science", "degree_type": "BSc", "student_username": "sem.ada",
                             "supervisor_username": "sem.supervisor", "semester": semester})
            return SimpleUploadedFile("projects.csv", out.getvalue().encode("utf-8"))

        self.assertEqual(import_archived_projects(upload("26b")), (1, []))
        self.assertEqual(ArchivedProject.objects.get(title="Imported 26b").semester, self.b)
        imported, errors = import_archived_projects(upload("25C"))
        self.assertEqual(imported, 0)
        self.assertIn('No semester "25C"', errors[0][1])
        self.assertEqual(import_archived_projects(upload(""))[0], 1)

    def test_coordinator_and_admin_menus_link_to_semesters(self):
        for user in (self.coordinator, self.admin):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertContains(self.client.get(reverse("dashboard")), f'href="{reverse("semesters")}"')
        self.client.force_login(self.supervisor)
        self.assertNotContains(self.client.get(reverse("dashboard")), f'href="{reverse("semesters")}"')

    def test_deadlines_page_offers_the_semester(self):
        self.client.force_login(self.coordinator)
        url = reverse("faculty_deadlines")
        self.client.post(url, {"action": "add", "name": "Chapter 2", "due_date": "2026-03-01", "semester": self.a.pk})
        deadline = ProjectDeadline.objects.get(name="Chapter 2")
        self.assertEqual(deadline.semester, self.a)
        self.assertContains(self.client.get(url), "26A")
        self.assertEqual(self.milestone_names(self.other_project), set())
