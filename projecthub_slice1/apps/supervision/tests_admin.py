"""Meeting records and their versions are view-only in the Django admin."""

from datetime import timedelta

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.projects.models import Project

from .models import MeetingRecordEdit, SupervisionMeeting


class MeetingRecordAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Faculty of Computing and Applied Sciences")
        department = Department.objects.create(faculty=faculty, name="Computer Science")
        programme = Programme.objects.create(department=department, name="Computer Science", degree_type="BSc")
        student = User.objects.create(username="amina", role=Role.STUDENT)
        StudentProfile.objects.create(user=student, student_number="BU/22/CS/1", programme=programme)
        project = Project.objects.create(student=student, title="Attendance tracker",
                                         department=department, programme=programme)
        cls.meeting = SupervisionMeeting.objects.create(project=project, scheduled_for=timezone.now() - timedelta(days=1),
                                                        discussion="Chapter two reviewed")
        cls.edit = MeetingRecordEdit.objects.create(meeting=cls.meeting, changes={"discussion": {"from": "", "to": "x"}})
        cls.admin_user = User.objects.create_superuser(username="site.admin", password="test-password")

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_meeting_record_and_its_versions_cannot_be_added_changed_or_deleted(self):
        change_url = reverse("admin:supervision_supervisionmeeting_change", args=[self.meeting.pk])
        view = self.client.get(change_url)
        add = self.client.post(reverse("admin:supervision_supervisionmeeting_add"), {"discussion": "Invented"})
        change = self.client.post(change_url, {
            "discussion": "Rewritten",
            "edits-TOTAL_FORMS": "1", "edits-INITIAL_FORMS": "1",
            "edits-0-id": self.edit.pk, "edits-0-meeting": self.meeting.pk, "edits-0-DELETE": "on",
        })
        delete = self.client.post(reverse("admin:supervision_supervisionmeeting_delete", args=[self.meeting.pk]),
                                  {"post": "yes"})
        # The list page itself is not opened: its date_hierarchy needs MySQL time zone tables.
        actions = admin.site._registry[SupervisionMeeting].get_actions(view.wsgi_request)

        self.assertEqual(view.status_code, 200)
        self.assertEqual((add.status_code, change.status_code, delete.status_code), (403, 403, 403))
        self.assertNotIn("delete_selected", actions)
        self.assertEqual(SupervisionMeeting.objects.count(), 1)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.discussion, "Chapter two reviewed")
        self.assertTrue(MeetingRecordEdit.objects.filter(pk=self.edit.pk).exists())
