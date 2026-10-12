"""Screenshots and demo videos on running and archived projects (D-30)."""

import shutil
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.demo_pdf import demo_png
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent

from .models import ArchivedProject, Project, ProjectMedia, ProjectStage
from .services import sign_off_completion

MEDIA = tempfile.mkdtemp(prefix="projecthub-media-tests-")
PNG = demo_png(8, 6)
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def png(name="screen.png", content=PNG):
    return SimpleUploadedFile(name, content, content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA)
class ProjectMediaTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Media Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        other = Department.objects.create(faculty=faculty, name="Law")
        programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.student = User.objects.create(username="ada", role=Role.STUDENT)
        StudentProfile.objects.create(user=cls.student, student_number="BU/22A/CS/1001", programme=programme)
        cls.reader = User.objects.create(username="reader", role=Role.STUDENT)
        cls.supervisor = User.objects.create(username="okoro", role=Role.SUPERVISOR, department=cls.department)
        cls.hod = User.objects.create(username="hod", role=Role.HOD, department=cls.department)
        cls.outsider = User.objects.create(username="law.lecturer", role=Role.SUPERVISOR, department=other)
        cls.admin = User.objects.create(username="admin.user", role=Role.ADMIN)
        cls.project = Project.objects.create(student=cls.student, title="Library Seat Booking", stage=ProjectStage.IN_PROGRESS,
                                             department=cls.department, programme=programme, supervisor=cls.supervisor)

    def add(self, user=None, **data):
        self.client.force_login(user or self.student)
        fields = {"kind": "image", "caption": "Login screen", "visibility": "baze_users", "video_url": "", **data}
        return self.client.post(reverse("add_project_media", args=[self.project.pk]), fields)

    def test_the_student_adds_a_screenshot_and_it_is_served_safely(self):
        response = self.add(file=png())
        self.assertRedirects(response, reverse("my_project"))
        item = ProjectMedia.objects.get()
        self.assertEqual((item.kind, item.project, item.uploaded_by), ("image", self.project, self.student))
        self.assertTrue(AuditEvent.objects.filter(action="project.media_added").exists())
        self.assertContains(self.client.get(reverse("my_project")), f'src="{reverse("project_media_file", args=[item.pk])}"')

        served = self.client.get(reverse("project_media_file", args=[item.pk]))
        self.assertEqual((served["Content-Type"], served["X-Content-Type-Options"], served["Content-Disposition"]),
                         ("image/png", "nosniff", "inline"))
        self.assertEqual(b"".join(served.streaming_content), PNG)

    def test_running_project_media_is_for_the_projects_people_only(self):
        self.add(file=png())
        item = ProjectMedia.objects.get()
        file_url = reverse("project_media_file", args=[item.pk])
        page_url = reverse("current_project_detail", args=[self.project.pk])
        for user, allowed in ((self.student, True), (self.supervisor, True), (self.hod, True), (self.admin, True),
                              (self.reader, False), (self.outsider, False)):
            with self.subTest(user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(file_url).status_code, 200 if allowed else 404)
                self.assertEqual(file_url in self.client.get(page_url).content.decode(), allowed)

    def test_a_demo_video_can_be_a_link_or_an_upload(self):
        self.assertRedirects(self.add(kind="video", caption="Full demo", video_url="https://youtu.be/abc123"), reverse("my_project"))
        self.assertRedirects(self.add(kind="video", caption="Walkthrough", file=SimpleUploadedFile("demo.mp4", MP4)), reverse("my_project"))
        self.assertContains(self.client.get(reverse("my_project")), 'href="https://youtu.be/abc123"')
        video = ProjectMedia.objects.get(caption="Walkthrough")
        self.assertEqual(self.client.get(reverse("project_media_file", args=[video.pk]))["Content-Type"], "video/mp4")

    def test_wrong_files_and_links_are_refused(self):
        cases = (
            ({"file": png("photo.png", b"<script>alert(1)</script>")}, "not a real image or video"),
            ({"file": png("photo.gif", PNG)}, "Choose a JPG, JPEG, PNG, WEBP file"),
            ({"file": png("big.png", PNG + b"\x00" * (5 * 1024 * 1024))}, "Images must be 5 MB or smaller"),
            ({"video_url": "https://youtu.be/x"}, "A link can only be given for a video"),
            ({"kind": "video", "video_url": "http://youtu.be/x"}, "Use an https link from YouTube, Google Drive or Vimeo"),
            ({"kind": "video", "video_url": "https://evil.example/watch"}, "Use an https link from YouTube, Google Drive or Vimeo"),
            ({"kind": "video", "video_url": "https://youtu.be/x", "file": SimpleUploadedFile("demo.mp4", MP4)}, "not both"),
        )
        for data, message in cases:
            with self.subTest(message):
                self.assertContains(self.add(**data), message)
        self.assertFalse(ProjectMedia.objects.exists())

    def test_at_most_six_screenshots(self):
        for number in range(6):
            self.add(file=png(f"s{number}.png"), caption=f"Screen {number}")
        self.assertContains(self.add(file=png("s7.png")), "already has the most screenshots allowed (6)")
        self.assertEqual(ProjectMedia.objects.count(), 6)

    def test_only_the_owner_or_an_admin_removes_media(self):
        self.add(file=png())
        item = ProjectMedia.objects.get()
        path = Path(item.file.path)
        self.client.force_login(self.reader)
        self.assertEqual(self.client.post(reverse("remove_project_media", args=[item.pk])).status_code, 403)
        self.client.force_login(self.student)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(reverse("remove_project_media", args=[item.pk])), reverse("my_project"))
        self.assertFalse(ProjectMedia.objects.exists())
        self.assertFalse(path.exists())
        self.assertTrue(AuditEvent.objects.filter(action="project.media_removed").exists())

    def test_media_moves_to_the_archive_and_follows_its_visibility(self):
        self.add(file=png(), caption="Public screen")
        self.add(file=png("staff.png"), caption="Staff screen", visibility="staff_only")
        Project.objects.filter(pk=self.project.pk).update(stage=ProjectStage.DEFENDED)
        _, archived = sign_off_completion(self.project, self.hod, date(2026, 7, 1), no_gap=True)
        self.assertEqual(set(archived.media.values_list("caption", flat=True)), {"Public screen", "Staff screen"})
        self.assertFalse(ProjectMedia.objects.filter(project__isnull=False).exists())

        page_url = reverse("past_project_detail", args=[archived.pk])
        self.client.force_login(self.reader)
        page = self.client.get(page_url)
        self.assertContains(page, "Public screen")
        self.assertNotContains(page, "Staff screen")
        self.client.force_login(self.supervisor)
        self.assertContains(self.client.get(page_url), "Staff screen")

    def test_only_an_admin_adds_media_to_an_archived_project(self):
        archived = ArchivedProject.objects.create(title="Old topic", student=self.student, department=self.department,
                                                  programme=self.project.programme, year=2024)
        url = reverse("add_archived_media", args=[archived.pk])
        data = {"kind": "image", "caption": "Old screen", "visibility": "baze_users", "file": png()}
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(url, data).status_code, 403)
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(url, {**data, "file": png()}), reverse("past_project_detail", args=[archived.pk]))
        self.assertContains(self.client.get(reverse("past_project_detail", args=[archived.pk])), "Add screenshot or video")


@override_settings(MEDIA_ROOT=MEDIA)
class DemoMediaTests(TestCase):
    def test_seed_adds_a_demo_screenshot_and_purge_removes_it(self):
        call_command("seed_demo", "--force", stdout=StringIO())
        item = ProjectMedia.objects.get(is_demo=True)
        path = Path(item.file.path)
        self.assertTrue(path.read_bytes().startswith(b"\x89PNG"))
        with self.captureOnCommitCallbacks(execute=True):
            call_command("purge_demo", stdout=StringIO())
        self.assertFalse(ProjectMedia.objects.exists())
        self.assertFalse(path.exists())
