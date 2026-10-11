import tempfile
from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, SupervisorProfile, User
from apps.projects.models import Project, ProjectMilestone, ProjectStage, ProjectStatusEvent, ProjectSupervisorAssignment

from .models import (
    Announcement, AnnouncementAcknowledgement, MeetingRequest, Notification, NotificationKind, SharedResource,
    SupervisionMeeting, SupervisorAvailability,
)
from .services import notify


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
        )
        return user

    def test_the_author_is_not_asked_to_acknowledge_their_own_notice(self):
        notice = Announcement.objects.create(
            author=self.supervisor, project=self.project, department=self.department,
            requires_acknowledgement=True, title="Bring chapter two", body="Bring a printed copy on Thursday.",
        )
        self.client.force_login(self.supervisor)
        page = self.client.get(reverse("announcements"))
        self.assertContains(page, "Bring chapter two")
        self.assertNotContains(page, "Acknowledge notice")
        self.assertContains(page, "You posted this notice")
        ack = self.client.post(reverse("announcements"), {"action": "acknowledge", "notice_id": notice.pk})
        self.assertEqual(ack.status_code, 403)
        self.assertFalse(AnnouncementAcknowledgement.objects.filter(announcement=notice, user=self.supervisor).exists())

        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("announcements")), "Acknowledge notice")
        self.client.post(reverse("announcements"), {"action": "acknowledge", "notice_id": notice.pk})
        self.assertIsNotNone(AnnouncementAcknowledgement.objects.get(announcement=notice, user=self.student).acknowledged_at)

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

    def test_meeting_requests_have_no_entry_point(self):
        # Booking from availability is not built (docs/known_limits.md). The model is kept for
        # later, but there is no URL, link or form that reaches it.
        with self.assertRaises(NoReverseMatch):
            reverse("request_meeting", args=[self.project.pk])
        self.client.force_login(self.student)
        response = self.client.post(f"/supervision/projects/{self.project.pk}/request-meeting/", {"message": "Hi"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(MeetingRequest.objects.count(), 0)
        for page in ("student_portal", "my_project", "announcements", "guidelines"):
            with self.subTest(page=page):
                self.assertNotContains(self.client.get(reverse(page)), "request-meeting")

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

    def test_administrator_sees_the_general_guide_but_not_supervision_resources(self):
        self.client.force_login(self.supervisor)
        self.client.post(reverse("announcements"), {
            "action": "publish_resource", "title": "Private chapter feedback", "description": "",
            "url": "", "project_targets": [str(self.project.pk)],
            "file": SimpleUploadedFile("feedback.pdf", b"feedback", content_type="application/pdf"),
        })
        resource = SharedResource.objects.get(title="Private chapter feedback")
        self.client.force_login(User.objects.create(username="guide.admin", role=Role.ADMIN))

        guide = self.client.get(reverse("guidelines"))

        self.assertContains(guide, "Project workflow")
        self.assertNotContains(guide, "Shared guide documents")
        self.assertNotContains(guide, "Private chapter feedback")
        self.assertEqual(self.client.get(reverse("download_shared_resource", args=[resource.pk])).status_code, 403)

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

    def test_meeting_records_are_visible_only_to_the_people_r33_names(self):
        meeting = SupervisionMeeting.objects.create(
            project=self.project, scheduled_for=timezone.now(), status="held",
            discussion="Private discussion notes", recorded_by=self.supervisor,
        )
        other_faculty = Faculty.objects.create(name="Law")
        other_department = Department.objects.create(faculty=other_faculty, name="Private Law")
        allowed = {
            "own student": self.student,
            "assigned supervisor": self.supervisor,
            "department coordinator": User.objects.create(
                username="r33.coordinator", role=Role.COORDINATOR, department=self.department
            ),
            "department HOD": User.objects.create(username="r33.hod", role=Role.HOD, department=self.department),
        }
        refused = {
            "another student": self.second_student,
            "another supervisor in the department": User.objects.create(
                username="r33.supervisor", role=Role.SUPERVISOR, department=self.department
            ),
            "coordinator of another department": User.objects.create(
                username="r33.outside", role=Role.COORDINATOR, department=other_department
            ),
            "HOD of another department": User.objects.create(
                username="r33.outside.hod", role=Role.HOD, department=other_department
            ),
            "coordinator with no department": User.objects.create(username="r33.nodept", role=Role.COORDINATOR),
            "administrator": User.objects.create(username="r33.admin", role=Role.ADMIN),
        }
        # The list links to each record; the record page shows the discussion notes.
        pages = {
            reverse("project_meetings", args=[self.project.pk]): reverse("meeting_detail", args=[meeting.pk]),
            reverse("meeting_detail", args=[meeting.pk]): "Private discussion notes",
        }

        for label, user in allowed.items():
            self.client.force_login(user)
            for url, expected in pages.items():
                with self.subTest(user=label, url=url):
                    self.assertContains(self.client.get(url), expected)
        for label, user in refused.items():
            self.client.force_login(user)
            for url in pages:
                with self.subTest(user=label, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 403)
                    self.assertNotContains(response, "Private discussion notes", status_code=403)


class RunAutomationTests(TestCase):
    """run_automation flags three things, notifies the right people, and never repeats itself within 24 h."""

    COMMAND = "apps.supervision.management.commands.run_automation"

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        faculty = Faculty.objects.create(name="Automation Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Automation Department")
        other_department = Department.objects.create(faculty=faculty, name="Other Automation Department")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.supervisor = User.objects.create(username="auto.supervisor", role=Role.SUPERVISOR, department=cls.department)
        cls.coordinator = User.objects.create(username="auto.coordinator", role=Role.COORDINATOR, department=cls.department)
        User.objects.create(username="auto.other.coordinator", role=Role.COORDINATOR, department=other_department)
        cls.admin = User.objects.create(username="auto.admin", role=Role.ADMIN)
        User.objects.create(username="auto.retired.admin", role=Role.ADMIN, is_active=False)

        def student(username, number, status=StudentProfile.RegistrationStatus.APPROVED, joined_hours_ago=500,
                    is_demo=False, **profile):
            user = User.objects.create(
                username=username, role=Role.STUDENT, date_joined=now - timedelta(hours=joined_hours_ago), is_demo=is_demo,
            )
            StudentProfile.objects.create(
                user=user, student_number=number, programme=cls.programme, registration_status=status, **profile
            )
            return user

        pending = StudentProfile.RegistrationStatus.PENDING
        cls.waiting_long = student("auto.waiting.long", "BU/26/A/1", pending, joined_hours_ago=49)
        student("auto.waiting.short", "BU/26/A/2", pending, joined_hours_ago=47)
        student("auto.waiting.demo", "BU/26/A/3", pending, joined_hours_ago=200, is_demo=True)
        cls.at_risk_student = student("auto.at.risk", "BU/26/A/4")
        cls.reader = student("auto.reader", "BU/26/A/5")
        cls.acknowledged = student("auto.acknowledged", "BU/26/A/6")
        student("auto.graduate", "BU/26/A/7", student_status=StudentProfile.Status.GRADUATED)

        # At risk: no held meeting in the 30 days since assignment (+40) and 3 overdue milestones (+30) = 70.
        cls.at_risk = Project.objects.create(
            student=cls.at_risk_student, title="Stalled project", department=cls.department,
            programme=cls.programme, supervisor=cls.supervisor, stage=ProjectStage.IN_PROGRESS,
        )
        ProjectStatusEvent.objects.create(project=cls.at_risk, to_stage=ProjectStage.IN_PROGRESS)
        assignment = ProjectSupervisorAssignment.objects.create(project=cls.at_risk, supervisor=cls.supervisor)
        ProjectSupervisorAssignment.objects.filter(pk=assignment.pk).update(assigned_at=now - timedelta(days=30))
        for number in range(3):
            ProjectMilestone.objects.create(project=cls.at_risk, name=f"Chapter {number}", due_date=date(2020, 1, 1))
        # On track: brand new, nothing overdue.
        Project.objects.create(
            student=cls.reader, title="Healthy project", department=cls.department, programme=cls.programme,
            supervisor=cls.supervisor, stage=ProjectStage.IN_PROGRESS,
        )

        def notice(title, hours_ago, requires_acknowledgement=True, project=None):
            item = Announcement.objects.create(
                author=cls.supervisor, department=cls.department, project=project, title=title, body="Read me.",
                requires_acknowledgement=requires_acknowledgement,
            )
            Announcement.objects.filter(pk=item.pk).update(created_at=now - timedelta(hours=hours_ago))
            return item

        cls.department_notice = notice("Department deadline", 72)
        cls.project_notice = notice("Your chapter two", 72, project=cls.at_risk)
        notice("Fresh notice", 2)
        notice("No acknowledgement needed", 72, requires_acknowledgement=False)
        AnnouncementAcknowledgement.objects.create(
            announcement=cls.department_notice, user=cls.acknowledged, acknowledged_at=now
        )

    def _run(self, *args):
        with self.assertLogs("projecthub.automation", "INFO") as logs:
            call_command("run_automation", *args, stdout=StringIO())
        return logs.output

    def _keep_connection(self):
        # The loop drops stale connections between runs. Inside a test transaction that would close the
        # connection the test is using (MySQL does; SQLite's in-memory test database ignores it).
        return mock.patch(f"{self.COMMAND}.close_old_connections")

    def _sent(self):
        return {
            (n.recipient.username, n.kind, n.object_type, n.object_id)
            for n in Notification.objects.select_related("recipient")
        }

    def test_first_run_notifies_the_right_people_for_each_flag(self):
        logs = self._run()

        project, user, notice = "projects.Project", "accounts.User", "supervision.Announcement"
        self.assertEqual(self._sent(), {
            ("auto.supervisor", NotificationKind.AT_RISK_PROJECT, project, str(self.at_risk.pk)),
            ("auto.coordinator", NotificationKind.AT_RISK_PROJECT, project, str(self.at_risk.pk)),
            ("auto.admin", NotificationKind.PENDING_REGISTRATION, user, str(self.waiting_long.pk)),
            ("auto.at.risk", NotificationKind.UNACKNOWLEDGED_NOTICE, notice, str(self.department_notice.pk)),
            ("auto.reader", NotificationKind.UNACKNOWLEDGED_NOTICE, notice, str(self.department_notice.pk)),
            ("auto.at.risk", NotificationKind.UNACKNOWLEDGED_NOTICE, notice, str(self.project_notice.pk)),
        })
        self.assertIn("run_automation: 6 new notifications", logs[-1])
        self.assertIn("at_risk_project: 1 flagged, 2 new, 0 already sent", logs[-1])
        self.assertIn("pending_registration: 1 flagged, 1 new, 0 already sent", logs[-1])
        self.assertIn("unacknowledged_notice: 2 flagged, 3 new, 0 already sent", logs[-1])
        alert = Notification.objects.get(recipient=self.supervisor)
        self.assertEqual(alert.title, "At risk (70/100): Stalled project")
        self.assertIn("3 overdue milestones (limit 3): +30", alert.body)
        self.assertEqual(alert.url, reverse("project_workflow", args=[self.at_risk.pk]))

    def test_second_run_creates_nothing_new(self):
        self._run()
        first = list(Notification.objects.order_by("pk").values_list("pk", flat=True))

        logs = self._run()

        self.assertEqual(list(Notification.objects.order_by("pk").values_list("pk", flat=True)), first)
        self.assertIn("run_automation: 0 new notifications", logs[-1])
        self.assertIn("at_risk_project: 1 flagged, 0 new, 2 already sent", logs[-1])

    def test_a_reminder_is_sent_again_once_24_hours_have_passed(self):
        self._run()
        Notification.objects.update(created_at=timezone.now() - timedelta(hours=25))

        self._run()

        self.assertEqual(Notification.objects.count(), 12)

    def test_acknowledging_stops_the_reminder(self):
        AnnouncementAcknowledgement.objects.create(
            announcement=self.department_notice, user=self.reader, acknowledged_at=timezone.now()
        )

        self._run()

        self.assertFalse(Notification.objects.filter(recipient=self.reader).exists())

    def test_notify_skips_only_the_same_recipient_kind_and_object_within_24_hours(self):
        now = timezone.now()
        kind = NotificationKind.PENDING_REGISTRATION

        self.assertIsNotNone(notify(self.admin, kind, self.waiting_long, title="First", now=now))
        self.assertIsNone(notify(self.admin, kind, self.waiting_long, title="Again", now=now + timedelta(hours=23)))
        self.assertIsNotNone(notify(self.coordinator, kind, self.waiting_long, title="Other recipient", now=now))
        self.assertIsNotNone(notify(self.admin, NotificationKind.AT_RISK_PROJECT, self.waiting_long, title="Other kind", now=now))
        self.assertIsNotNone(notify(self.admin, kind, self.reader, title="Other object", now=now))
        self.assertIsNotNone(notify(self.admin, kind, self.waiting_long, title="Next day", now=now + timedelta(hours=25)))

    def test_loop_runs_until_stopped(self):
        with mock.patch(f"{self.COMMAND}.time.sleep", side_effect=KeyboardInterrupt) as sleep, self._keep_connection():
            logs = self._run("--loop", "--interval", "5")

        sleep.assert_called_once_with(5)
        self.assertIn("looping every 5 seconds", logs[0])
        self.assertIn("run_automation: 6 new notifications", logs[1])
        self.assertIn("run_automation: stopped", logs[-1])

    def test_loop_keeps_going_after_a_failed_run(self):
        with mock.patch(f"{self.COMMAND}.run_once", side_effect=[RuntimeError("database away"), {}]) as run_once, \
                mock.patch(f"{self.COMMAND}.time.sleep", side_effect=[None, KeyboardInterrupt]), self._keep_connection():
            logs = self._run("--loop")

        self.assertEqual(run_once.call_count, 2)
        self.assertTrue(any("run failed" in line for line in logs))

    def test_interval_must_be_positive(self):
        with self.assertRaises(CommandError):
            call_command("run_automation", "--loop", "--interval", "0", stdout=StringIO())

    def test_mark_one_alert_read_and_never_someone_elses(self):
        self._run()
        mine = Notification.objects.filter(recipient=self.supervisor).first()
        theirs = Notification.objects.filter(recipient=self.coordinator).first()
        self.client.force_login(self.supervisor)

        self.client.post(reverse("notifications"), {"action": "read", "notification_id": mine.pk})
        self.client.post(reverse("notifications"), {"action": "read", "notification_id": theirs.pk})

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertIsNotNone(mine.read_at)
        self.assertIsNone(theirs.read_at)
        self.assertEqual(self.client.get(reverse("api_summary")).json()["unread_notifications"], 0)

    def test_every_role_has_the_alerts_link_in_the_menu(self):
        for user in (self.supervisor, self.coordinator, self.admin, self.reader):
            self.client.force_login(user)
            self.assertContains(self.client.get(reverse("announcements")), f'href="{reverse("notifications")}"', msg_prefix=user.username)

    def test_alerts_page_shows_only_your_own_and_marks_them_read(self):
        self._run()
        self.client.force_login(self.coordinator)

        response = self.client.get(reverse("notifications"))

        self.assertContains(response, "At risk (70/100): Stalled project")
        self.assertNotContains(response, "Registration waiting")
        self.assertContains(response, '<span class="nav-count" data-counter="unread_notifications">1</span>')

        self.client.post(reverse("notifications"), {"action": "read_all"})

        self.assertFalse(Notification.objects.filter(recipient=self.coordinator, read_at__isnull=True).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.supervisor, read_at__isnull=False).exists())
