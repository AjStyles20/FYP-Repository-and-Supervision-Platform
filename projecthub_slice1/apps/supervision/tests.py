import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, SupervisorProfile, User
from apps.projects.models import Project, ProjectStage

from .models import Announcement, MeetingRequest, SharedResource, SupervisionMeeting, SupervisorAvailability


class SupervisorStudentWorkflowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_temp_dir = tempfile.TemporaryDirectory()
        cls.media_settings = override_settings(MEDIA_ROOT=cls.media_temp_dir.name)
        cls.media_settings.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_settings.disable()
        cls.media_temp_dir.cleanup()

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Computing")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.supervisor = User.objects.create_user(
            username="supervisor.test", password="test-password", first_name="Ada", last_name="Supervisor",
            role=Role.SUPERVISOR, department=cls.department,
        )
        cls.student = cls.make_student("student.one", "One")
        cls.second_student = cls.make_student("student.two", "Two")
        cls.project = Project.objects.create(
            student=cls.student, title="Student One project", description="Initial summary", department=cls.department,
            programme=cls.programme, supervisor=cls.supervisor, stage=ProjectStage.IN_PROGRESS,
        )
        cls.second_project = Project.objects.create(
            student=cls.second_student, title="Student Two project", department=cls.department,
            programme=cls.programme, supervisor=cls.supervisor, stage=ProjectStage.IN_PROGRESS,
        )

    @classmethod
    def make_student(cls, username, last_name):
        user = User.objects.create_user(
            username=username, password="test-password", first_name="Student", last_name=last_name,
            role=Role.STUDENT, email=f"{username}@bazeuniversity.edu.ng",
        )
        StudentProfile.objects.create(
            user=user, student_number=f"BU/26/CS/{username[-1] * 4}", programme=cls.programme,
            contact_consent=False,
        )
        return user

    def test_saving_availability_notifies_current_students(self):
        self.client.force_login(self.supervisor)
        response = self.client.post(reverse("supervisor_availability"), {
            "action": "save_slot", "weekday": timezone.localdate().weekday(), "start_time": "10:00",
            "end_time": "11:00", "venue": "Room 204", "mode": "physical", "is_active": "on",
        })

        self.assertRedirects(response, reverse("supervisor_availability"))
        self.assertEqual(SupervisorAvailability.objects.filter(supervisor=self.supervisor).count(), 1)
        self.assertTrue(Announcement.objects.filter(project=self.project, title="Supervisor availability updated").exists())
        self.assertTrue(Announcement.objects.filter(project=self.second_project, title="Supervisor availability updated").exists())
        self.client.force_login(self.student)
        portal = self.client.get(reverse("student_portal"))
        self.assertContains(portal, "Supervisor availability updated")
        self.assertContains(portal, "1 new update")

    def test_students_cannot_submit_meeting_requests(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("request_meeting", args=[self.project.pk]), {
            "message": "Please meet with me",
        })

        self.assertEqual(response.status_code, 403)
        self.assertEqual(MeetingRequest.objects.count(), 0)

    def test_supervisor_schedules_meeting_and_student_gets_notice(self):
        when = timezone.localtime(timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        self.client.force_login(self.supervisor)
        response = self.client.post(reverse("project_meetings", args=[self.project.pk]), {
            "scheduled_for": when, "duration_minutes": "60", "venue": "Room 204", "mode": "physical",
            "status": "scheduled", "agenda": "Review chapter two", "discussion": "",
            "corrective_action": "", "next_steps": "", "next_meeting_at": "",
        })

        self.assertRedirects(response, reverse("project_meetings", args=[self.project.pk]))
        self.assertEqual(SupervisionMeeting.objects.filter(project=self.project).count(), 1)
        self.assertTrue(Announcement.objects.filter(project=self.project, title="A supervision meeting was scheduled").exists())
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("student_portal")), "A supervision meeting was scheduled")

    def test_conflicting_supervisor_meeting_time_is_rejected(self):
        when = timezone.localtime(timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)
        SupervisionMeeting.objects.create(project=self.project, scheduled_for=when, duration_minutes=60)
        conflicting_when = (when + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
        self.client.force_login(self.supervisor)
        response = self.client.post(reverse("project_meetings", args=[self.second_project.pk]), {
            "scheduled_for": conflicting_when, "duration_minutes": "60", "venue": "Room 204", "mode": "physical",
            "status": "scheduled", "agenda": "Review", "discussion": "", "corrective_action": "",
            "next_steps": "", "next_meeting_at": "",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overlaps another scheduled meeting")
        self.assertEqual(SupervisionMeeting.objects.count(), 1)

    def test_supervisor_can_upload_targeted_resource_and_students_can_download_it(self):
        self.client.force_login(self.supervisor)
        response = self.client.post(reverse("announcements"), {
            "action": "publish_resource", "title": "Literature review guide", "description": "Use this for chapter two.",
            "url": "", "project_targets": [str(self.project.pk), str(self.second_project.pk)],
            "file": SimpleUploadedFile("guide.pdf", b"guide contents", content_type="application/pdf"),
        })

        self.assertRedirects(response, reverse("announcements"))
        resource = SharedResource.objects.get(title="Literature review guide")
        self.assertEqual(resource.projects.count(), 2)
        self.assertEqual(Announcement.objects.filter(title="New shared resource: Literature review guide").count(), 2)
        self.client.force_login(self.student)
        portal = self.client.get(reverse("student_portal"))
        self.assertContains(portal, "Literature review guide")
        self.assertContains(self.client.get(reverse("guidelines")), "Literature review guide")
        download = self.client.get(reverse("download_shared_resource", args=[resource.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertIn(b"guide contents", b"".join(download.streaming_content))

        self.client.force_login(self.supervisor)
        edit = self.client.post(reverse("edit_shared_resource", args=[resource.pk]), {
            "title": "Revised literature review guide", "description": "Updated format.", "url": "",
            "project_targets": [str(self.project.pk), str(self.second_project.pk)],
        })
        self.assertRedirects(edit, reverse("announcements"))
        self.assertTrue(Announcement.objects.filter(title="Shared resource updated: Revised literature review guide").exists())

    def test_resource_reaches_only_the_supervisees_it_was_sent_to(self):
        other_supervisor = User.objects.create_user(
            username="supervisor.other", role=Role.SUPERVISOR, department=self.department,
        )
        outsider = self.make_student("student.3", "Three")
        Project.objects.create(
            student=outsider, title="Student Three project", department=self.department,
            programme=self.programme, supervisor=other_supervisor, stage=ProjectStage.IN_PROGRESS,
        )
        self.client.force_login(self.supervisor)
        self.client.post(reverse("announcements"), {
            "action": "publish_resource", "title": "Chapter one template", "description": "", "url": "",
            "project_targets": [str(self.project.pk)],
            "file": SimpleUploadedFile("template.docx", b"template", content_type="application/octet-stream"),
        })
        resource = SharedResource.objects.get(title="Chapter one template")
        self.assertEqual(resource.department, self.department)
        # A department-wide resource with no targets (e.g. added in the admin) reaches no student.
        untargeted = SharedResource.objects.create(
            author=self.supervisor, department=self.department, title="Untargeted department file",
            file=SimpleUploadedFile("dept.pdf", b"dept"),
        )

        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("guidelines")), "Chapter one template")
        download = self.client.get(reverse("download_shared_resource", args=[resource.pk]))
        self.assertEqual(b"".join(download.streaming_content), b"template")
        self.assertEqual(self.client.get(reverse("download_shared_resource", args=[untargeted.pk])).status_code, 403)

        # Same supervisor but not a target, and same department but another supervisor's student.
        for user in (self.second_student, outsider):
            with self.subTest(student=user.username):
                self.client.force_login(user)
                self.assertNotContains(self.client.get(reverse("student_portal")), "Chapter one template")
                guide = self.client.get(reverse("guidelines"))
                self.assertNotContains(guide, "Chapter one template")
                self.assertNotContains(guide, "Untargeted department file")
                self.assertEqual(
                    self.client.get(reverse("download_shared_resource", args=[resource.pk])).status_code, 403
                )

    def test_approval_criteria_are_editable_visible_and_notified(self):
        self.client.force_login(self.supervisor)
        response = self.client.post(reverse("approval_policy"), {
            "approval_method": "literature_review",
            "approval_criteria": "Use at least ten recent sources and identify a clear research gap.",
        })

        self.assertRedirects(response, reverse("approval_policy"))
        profile = SupervisorProfile.objects.get(user=self.supervisor)
        self.assertIn("ten recent sources", profile.approval_criteria)
        self.assertTrue(Announcement.objects.filter(project=self.project, title="Supervisor approval criteria updated").exists())
        self.client.force_login(self.student)
        workflow = self.client.get(reverse("project_workflow", args=[self.project.pk]))
        self.assertContains(workflow, "ten recent sources")

