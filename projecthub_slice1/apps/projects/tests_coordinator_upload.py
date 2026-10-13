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


@override_settings(MEDIA_ROOT=MEDIA)
class ProjectFileListTests(TestCase):
    """Staff see a running project's files on the workflow page; archived files name their uploader."""

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="File List Faculty")
        department = Department.objects.create(faculty=faculty, name="Computer Science")
        other = Department.objects.create(faculty=faculty, name="Software Engineering")
        programme = Programme.objects.create(department=department, name="Computer Science", degree_type="BSc")
        cls.student = User.objects.create(username="list.student", first_name="Ada", last_name="Bello", role=Role.STUDENT)
        StudentProfile.objects.create(user=cls.student, student_number="BU/22A/CS/3002", programme=programme)
        cls.supervisor = User.objects.create(username="list.supervisor", role=Role.SUPERVISOR, department=department)
        cls.coordinator = User.objects.create(username="list.coordinator", first_name="Grace", last_name="Okafor",
                                              role=Role.COORDINATOR, department=department)
        cls.hod = User.objects.create(username="list.hod", role=Role.HOD, department=department)
        cls.admin = User.objects.create(username="list.admin", role=Role.ADMIN)
        cls.other_coordinator = User.objects.create(username="list.other.coordinator", role=Role.COORDINATOR, department=other)
        cls.other_hod = User.objects.create(username="list.other.hod", role=Role.HOD, department=other)
        cls.project = Project.objects.create(
            student=cls.student, title="Clinic Queue Manager", department=department, programme=programme,
            supervisor=cls.supervisor, stage=ProjectStage.IN_PROGRESS,
        )

    def setUp(self):
        self.workflow = reverse("project_workflow", args=[self.project.pk])

    def add_document(self, title, uploader, document_type=DocumentType.OTHER):
        return ProjectDocument.objects.create(
            project=self.project, title=title, document_type=document_type, file=report(f"{title}.pdf"),
            uploaded_by=uploader, visibility=ProjectDocument.Visibility.STAFF_ONLY,
        )

    def test_department_staff_see_the_files_newest_first(self):
        older = self.add_document("Draft chapter", self.student)
        newer = self.add_document("Final report", self.coordinator, DocumentType.REPORT)
        for user in (self.supervisor, self.coordinator, self.hod, self.admin):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                page = self.client.get(self.workflow)
                self.assertEqual(page.context["documents"], [newer, older])
                self.assertContains(page, "Project files")
                self.assertContains(page, "Uploaded by Grace Okafor")  # the coordinator's upload
                self.assertContains(page, "Uploaded by Ada Bello")
                self.assertContains(page, "Final report")
                self.assertContains(page, reverse("download_project_document", args=[newer.pk]))

    def test_an_empty_list_says_so(self):
        self.client.force_login(self.coordinator)
        self.assertContains(self.client.get(self.workflow), "No files yet.")

    def test_students_other_departments_and_visitors_do_not_see_the_list(self):
        document = self.add_document("Final report", self.coordinator, DocumentType.REPORT)
        download = reverse("download_project_document", args=[document.pk])

        self.client.force_login(self.student)
        page = self.client.get(self.workflow)
        self.assertIsNone(page.context["documents"])
        self.assertNotContains(page, "Project files")
        self.assertNotContains(page, download)

        for user in (self.other_coordinator, self.other_hod):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.workflow).status_code, 403)

        self.client.logout()
        response = self.client.get(self.workflow)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_the_archived_page_names_who_uploaded_each_file(self):
        self.add_document("Final report", self.coordinator, DocumentType.REPORT)
        self.add_document("Abstract", self.student)
        Project.objects.filter(pk=self.project.pk).update(stage=ProjectStage.DEFENDED)
        self.project.refresh_from_db()
        _, archived = sign_off_completion(self.project, self.hod, signed_on=date(2026, 10, 13), no_gap=True)

        self.client.force_login(self.supervisor)
        page = self.client.get(reverse("past_project_detail", args=[archived.pk]))

        self.assertContains(page, "Uploaded by Grace Okafor")
        self.assertContains(page, "Uploaded by Ada Bello")
