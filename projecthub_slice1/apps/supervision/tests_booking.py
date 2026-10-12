"""Students request a meeting in their supervisor's availability window; the supervisor decides (D-32)."""

from datetime import datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent
from apps.projects.models import Project, ProjectStage

from .models import MeetingRequest, Notification, NotificationKind, SupervisionMeeting, SupervisorAvailability


def next_weekday(weekday):
    today = timezone.localdate()
    return today + timedelta(days=(weekday - today.weekday()) % 7 or 7)


class MeetingBookingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Booking Faculty")
        department = Department.objects.create(faculty=faculty, name="Computer Science")
        programme = Programme.objects.create(department=department, name="Computer Science", degree_type="BSc")
        cls.supervisor = User.objects.create(username="okoro", first_name="A.", last_name="Okoro", role=Role.SUPERVISOR, department=department)
        cls.other_supervisor = User.objects.create(username="eze", role=Role.SUPERVISOR, department=department)
        cls.student = User.objects.create(username="ada", first_name="Ada", role=Role.STUDENT)
        StudentProfile.objects.create(user=cls.student, student_number="BU/22A/CS/1001", programme=programme)
        cls.other_student = User.objects.create(username="bola", role=Role.STUDENT)
        cls.project = Project.objects.create(student=cls.student, title="Seat booking", stage=ProjectStage.IN_PROGRESS,
                                             department=department, programme=programme, supervisor=cls.supervisor)
        cls.slot = SupervisorAvailability.objects.create(supervisor=cls.supervisor, weekday=1, start_time=time(10),
                                                         end_time=time(12), venue="Room B12")
        cls.tuesday = next_weekday(1)
        cls.url = reverse("project_meetings", args=[cls.project.pk])

    def request_meeting(self, user=None, **changes):
        self.client.force_login(user or self.student)
        data = {"action": "request_meeting", "availability": self.slot.pk, "requested_date": self.tuesday.isoformat(),
                "message": "Chapter two feedback", **changes}
        return self.client.post(self.url, data)

    def decide(self, decision, note="", user=None):
        self.client.force_login(user or self.supervisor)
        request = MeetingRequest.objects.get()
        return self.client.post(self.url, {"action": "decide_request", "request_id": request.pk, "decision": decision, "note": note})

    def test_the_student_requests_and_the_supervisor_is_alerted(self):
        self.client.force_login(self.student)
        self.assertContains(self.client.get(self.url), "Request a meeting")
        self.assertRedirects(self.request_meeting(), self.url)
        request = MeetingRequest.objects.get()
        self.assertEqual((request.status, request.student, request.requested_date), ("pending", self.student, self.tuesday))
        self.assertTrue(Notification.objects.filter(recipient=self.supervisor, kind=NotificationKind.MEETING_REQUESTED).exists())
        self.assertTrue(AuditEvent.objects.filter(action="meeting.requested").exists())

    def test_wrong_dates_and_repeats_are_refused(self):
        wednesday = self.tuesday + timedelta(days=1)
        self.assertContains(self.request_meeting(requested_date=wednesday.isoformat()), "falls on the selected availability day")
        self.assertContains(self.request_meeting(requested_date=(self.tuesday - timedelta(days=7 * 52)).isoformat()), "Choose a future date")
        self.request_meeting()
        self.assertContains(self.request_meeting(), "already asked for this time")
        self.assertEqual(MeetingRequest.objects.count(), 1)

    def test_a_busy_time_cannot_be_requested(self):
        start = timezone.make_aware(datetime.combine(self.tuesday, time(10, 30)))
        SupervisionMeeting.objects.create(project=self.project, scheduled_for=start, duration_minutes=30)
        self.assertContains(self.request_meeting(), "already has a meeting at that time")

    def test_accepting_schedules_the_meeting_and_tells_the_student(self):
        self.request_meeting()
        self.assertRedirects(self.decide("accept"), self.url)
        request = MeetingRequest.objects.get()
        meeting = request.meeting
        self.assertEqual(request.status, "approved")
        self.assertEqual((timezone.localtime(meeting.scheduled_for).date(), timezone.localtime(meeting.scheduled_for).time()),
                         (self.tuesday, time(10)))
        self.assertEqual((meeting.duration_minutes, meeting.venue, meeting.agenda), (120, "Room B12", "Chapter two feedback"))
        self.assertTrue(Notification.objects.filter(recipient=self.student, kind=NotificationKind.MEETING_REQUEST_DECIDED).exists())

    def test_declining_needs_a_reason_that_the_student_sees(self):
        self.request_meeting()
        self.decide("decline")
        self.assertEqual(MeetingRequest.objects.get().status, "pending")
        self.decide("decline", note="I am away that week; try the next Tuesday.")
        self.assertEqual(MeetingRequest.objects.get().status, "declined")
        self.assertFalse(SupervisionMeeting.objects.exists())
        self.client.force_login(self.student)
        self.assertContains(self.client.get(self.url), "I am away that week")

    def test_only_the_student_requests_and_only_their_supervisor_decides(self):
        self.client.force_login(self.other_student)
        self.assertEqual(self.client.post(self.url, {"action": "request_meeting"}).status_code, 403)
        self.request_meeting()
        self.client.force_login(self.student)
        response = self.client.post(self.url, {"action": "decide_request", "request_id": MeetingRequest.objects.get().pk, "decision": "accept"})
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.other_supervisor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(MeetingRequest.objects.get().status, "pending")

    def test_no_request_form_without_availability(self):
        SupervisorAvailability.objects.all().delete()
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(self.url), "Request a meeting")
