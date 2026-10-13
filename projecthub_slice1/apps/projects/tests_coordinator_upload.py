"""The department's coordinator may upload the final document; the HOD's sign-off still archives it."""

import shutil
import tempfile
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User

from .models import DocumentType, Project, ProjectDocument, ProjectStage
from .services import sign_off_completion

MEDIA = tempfile.mkdtemp(prefix="projecthub-coordinator-upload-")


def report(name="final.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 final report", content_type="application/pdf")


@override_settings(MEDIA_ROOT=MEDIA)
class CoordinatorUploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Upload Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        other = Department.objects.create(faculty=faculty, name="Software Engineering")
        programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.student = User.objects.create(username="upload.student", role=Role.STUDENT)
        StudentProfile.objects.create(user=cls.student, student_number="BU/22A/CS/3001", programme=programme)
        cls.supervisor = User.objects.create(username="upload.supervisor", role=Role.SUPERVISOR, department=cls.department)
        cls.coordinator = User.objects.create(username="upload.coordinator", role=Role.COORDINATOR, department=cls.department)
        cls.other_coordinator = User.objects.create(username="other.coordinator", role=Role.COORDINATOR, department=other)
        cls.hod = User.objects.create(username="upload.hod", role=Role.HOD, department=cls.department)
        cls.project = Project.objects.create(
            student=cls.student, title="Hostel Maintenance Tracker", department=cls.department, programme=programme,
            supervisor=cls.supervisor, stage=ProjectStage.IN_PROGRESS,
        )

    def set_stage(self, stage):
        Project.objects.filter(pk=self.project.pk).update(stage=stage)
        self.project.refresh_from_db()

    def upload(self, user, name="final.pdf"):
        self.client.force_login(user)
        return self.client.post(reverse("upload_project_document", args=[self.project.pk]),
                                {"title": "Final report", "document_type": DocumentType.REPORT, "file": report(name)})

    def test_the_departments_coordinator_uploads_the_final_document(self):
        workflow = reverse("project_workflow", args=[self.project.pk])
        upload_url = reverse("upload_project_document", args=[self.project.pk])
        for stage in (ProjectStage.IN_PROGRESS, ProjectStage.SUBMITTED, ProjectStage.DEFENDED):
            with self.subTest(stage=stage):
                self.set_stage(stage)
                self.client.force_login(self.coordinator)
                self.assertContains(self.client.get(workflow), "Upload final report")
                form_page = self.client.get(upload_url)
                self.assertEqual(form_page.context["form"]["document_type"].value(), DocumentType.REPORT)
                self.assertRedirects(self.upload(self.coordinator, f"{stage}.pdf"), workflow, fetch_redirect_response=False)
        documents = ProjectDocument.objects.filter(project=self.project)
        self.assertEqual(documents.count(), 3)
        self.assertTrue(all(document.uploaded_by == self.coordinator for document in documents))

    def test_not_before_the_project_is_in_progress(self):
        self.set_stage(ProjectStage.APPROVED)
        self.client.force_login(self.coordinator)
        self.assertNotContains(self.client.get(reverse("project_workflow", args=[self.project.pk])), "Upload final report")
        self.assertEqual(self.upload(self.coordinator).status_code, 403)
        self.assertFalse(ProjectDocument.objects.exists())

    def test_a_coordinator_from_another_department_cannot_upload(self):
        self.client.force_login(self.other_coordinator)
        self.assertEqual(self.client.get(reverse("upload_project_document", args=[self.project.pk])).status_code, 404)
        self.assertEqual(self.upload(self.other_coordinator).status_code, 404)
        self.assertFalse(ProjectDocument.objects.exists())

    def test_student_and_supervisor_behaviour_is_unchanged(self):
        self.assertRedirects(self.upload(self.student), reverse("my_project"), fetch_redirect_response=False)
        self.assertEqual(ProjectDocument.objects.get().uploaded_by, self.student)

        self.set_stage(ProjectStage.SUBMITTED)
        self.assertEqual(self.upload(self.student, "late.pdf").status_code, 403)
        self.assertEqual(self.upload(self.supervisor, "supervisor.pdf").status_code, 403)
        self.client.force_login(self.supervisor)
        self.assertNotContains(self.client.get(reverse("project_workflow", args=[self.project.pk])), "Upload final report")
        self.assertEqual(ProjectDocument.objects.count(), 1)

    def test_hod_sign_off_still_archives_the_coordinators_upload(self):
        self.set_stage(ProjectStage.DEFENDED)
        self.upload(self.coordinator)
        document = ProjectDocument.objects.get()

        _, archived = sign_off_completion(self.project, self.hod, signed_on=date(2026, 10, 13), no_gap=True)

        document.refresh_from_db()
        self.assertEqual((document.archived_project, document.project, document.uploaded_by), (archived, None, self.coordinator))
        self.project.refresh_from_db()
        self.assertTrue(self.project.archived)
