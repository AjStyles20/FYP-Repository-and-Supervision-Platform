"""Small list and file fixes: each supervisor named once, a year whenever graduation is verified,
and a clear page (not a server error) when a stored file is missing on disk."""

import shutil
import tempfile
from datetime import date

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.supervision.models import SharedResource

from .forms import CompletionForm
from .models import ArchivedProject, Project, ProjectDocument, ProjectMedia, ProjectStage, ProjectSupervisorAssignment
from .services import sign_off_completion
from .services.assignment import previous_supervisors_for

MEDIA = tempfile.mkdtemp(prefix="projecthub-list-fixes-")


@override_settings(MEDIA_ROOT=MEDIA)
class ListAndFileFixTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Fixes Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.student = User.objects.create(username="fix.student", role=Role.STUDENT)
        StudentProfile.objects.create(user=cls.student, student_number="BU/22A/CS/2001", programme=cls.programme)
        cls.first = User.objects.create(username="fix.first", last_name="Okoro", role=Role.SUPERVISOR, department=cls.department)
        cls.second = User.objects.create(username="fix.second", last_name="Bello", role=Role.SUPERVISOR, department=cls.department)
        cls.hod = User.objects.create(username="fix.hod", role=Role.HOD, department=cls.department)
        cls.project = Project.objects.create(
            student=cls.student, title="Exam Timetable Planner", department=cls.department, programme=cls.programme,
            supervisor=cls.second, stage=ProjectStage.DEFENDED,
        )

    # --- each supervisor named once ------------------------------------------------------------

    def test_earlier_supervisors_are_listed_once_and_never_include_the_final_one(self):
        ended = timezone.now()
        for supervisor in (self.first, self.second, self.first):
            ProjectSupervisorAssignment.objects.create(project=self.project, supervisor=supervisor, ended_at=ended)

        self.assertEqual(previous_supervisors_for(self.project), [self.first])

        _, archived = sign_off_completion(self.project, self.hod, signed_on=date(2026, 10, 5), no_gap=True)
        self.assertEqual(list(archived.previous_supervisors.all()), [self.first])

    def test_past_project_page_does_not_repeat_the_final_supervisor(self):
        archived = ArchivedProject.objects.create(
            title="Older record", year=2024, department=self.department, programme=self.programme,
            student=self.student, supervisor=self.second,
        )
        archived.previous_supervisors.set([self.first, self.second])
        self.client.force_login(self.hod)

        response = self.client.get(reverse("past_project_detail", args=[archived.pk]))

        self.assertEqual(response.context["previous_supervisors"], [self.first])

    # --- the graduation year ---------------------------------------------------------------------

    def test_graduation_verified_needs_a_year(self):
        form = CompletionForm(data={"signed_on": "2026-10-05", "no_gap": "on", "graduation_verified": "on"})
        self.assertFalse(form.is_valid())
        self.assertIn("graduation_year", form.errors)
        self.assertTrue(CompletionForm(data={"signed_on": "2026-10-05", "no_gap": "on", "graduation_verified": "on",
                                             "graduation_year": "2026"}).is_valid())
        self.assertTrue(CompletionForm(data={"signed_on": "2026-10-05", "no_gap": "on"}).is_valid())

        with self.assertRaises(ValidationError):
            sign_off_completion(self.project, self.hod, signed_on=date(2026, 10, 5), no_gap=True, graduation_verified=True)
        self.project.refresh_from_db()
        self.assertFalse(self.project.archived)

    # --- a missing file shows a clear page -------------------------------------------------------

    def _assert_missing_page(self, response):
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "no longer on the server", status_code=404)
        self.assertContains(response, "upload it again", status_code=404)

    def test_a_document_whose_file_is_gone_shows_a_clear_page(self):
        document = ProjectDocument.objects.create(
            project=self.project, title="Draft", document_type="report", uploaded_by=self.student,
            file=SimpleUploadedFile("draft.pdf", b"draft"), visibility=ProjectDocument.Visibility.STAFF_ONLY,
        )
        document.file.storage.delete(document.file.name)
        self.client.force_login(self.second)

        with self.assertLogs("apps.projects.files", "WARNING"):
            self._assert_missing_page(self.client.get(reverse("download_project_document", args=[document.pk])))

    def test_a_screenshot_whose_file_is_gone_shows_a_clear_page(self):
        item = ProjectMedia.objects.create(
            project=self.project, kind=ProjectMedia.Kind.IMAGE, caption="Login screen", uploaded_by=self.student,
            file=SimpleUploadedFile("screen.png", b"png"),
        )
        item.file.storage.delete(item.file.name)
        self.client.force_login(self.second)

        with self.assertLogs("apps.projects.files", "WARNING"):
            self._assert_missing_page(self.client.get(reverse("project_media_file", args=[item.pk])))

    def test_a_shared_resource_whose_file_is_gone_shows_a_clear_page(self):
        resource = SharedResource.objects.create(
            author=self.second, department=self.department, title="Report template",
            file=SimpleUploadedFile("template.pdf", b"template"),
        )
        resource.file.storage.delete(resource.file.name)
        self.client.force_login(self.second)

        with self.assertLogs("apps.projects.files", "WARNING"):
            self._assert_missing_page(self.client.get(reverse("download_shared_resource", args=[resource.pk])))
