"""Faculty deadlines, per-student milestones and reminders (D-33)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent
from apps.supervision.automation import flag_deadlines_soon
from apps.supervision.models import Notification, NotificationKind

from .models import Project, ProjectDeadline, ProjectMilestone, ProjectStage


class MilestoneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Computing")
        cls.cs = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.cyber = Department.objects.create(faculty=faculty, name="Cyber Security")
        law = Department.objects.create(faculty=Faculty.objects.create(name="Law"), name="Private Law")
        cls.cs_programme = Programme.objects.create(department=cls.cs, name="Computer Science", degree_type="BSc")
        cyber_programme = Programme.objects.create(department=cls.cyber, name="Cyber Security", degree_type="BSc")
        law_programme = Programme.objects.create(department=law, name="Law", degree_type="LLB")
        cls.coordinator = User.objects.create(username="coord", role=Role.COORDINATOR, department=cls.cyber, can_assign_supervisors=True)
        cls.supervisor = User.objects.create(username="okoro", role=Role.SUPERVISOR, department=cls.cs)
        cls.other_supervisor = User.objects.create(username="eze", role=Role.SUPERVISOR, department=cls.cs)
        cls.hod = User.objects.create(username="hod", role=Role.HOD, department=cls.cs)

        def project(name, programme, **extra):
            student = User.objects.create(username=name, role=Role.STUDENT)
            StudentProfile.objects.create(user=student, student_number=f"BU/22A/XX/{1000 + User.objects.count()}", programme=programme)
            return Project.objects.create(student=student, title=f"{name} project", stage=ProjectStage.IN_PROGRESS,
                                          department=programme.department, programme=programme, **extra)

        cls.cs_project = project("ada", cls.cs_programme, supervisor=cls.supervisor)
        cls.cyber_project = project("kemi", cyber_programme)
        cls.law_project = project("lola", law_programme)
        cls.archived_project = project("old", cls.cs_programme, archived=True)
        cls.due = timezone.localdate() + timedelta(days=30)

    def add_deadline(self, name="Chapter 1", due=None):
        self.client.force_login(self.coordinator)
        return self.client.post(reverse("faculty_deadlines"), {"action": "add", "name": name, "due_date": (due or self.due).isoformat()})

    def milestones_url(self, project=None):
        return reverse("project_milestones", args=[(project or self.cs_project).pk])

    def test_a_faculty_deadline_reaches_every_running_project_of_the_faculty(self):
        self.assertRedirects(self.add_deadline(), reverse("faculty_deadlines"))
        deadline = ProjectDeadline.objects.get()
        with_it = set(ProjectMilestone.objects.filter(deadline=deadline).values_list("project_id", flat=True))
        self.assertEqual(with_it, {self.cs_project.pk, self.cyber_project.pk})  # not Law, not archived
        self.assertTrue(AuditEvent.objects.filter(action="deadline.created").exists())

    def test_projects_started_later_get_the_deadlines(self):
        self.add_deadline()
        student = User.objects.create(username="new", role=Role.STUDENT)
        StudentProfile.objects.create(user=student, student_number="BU/23A/CS/2001", programme=self.cs_programme)
        self.client.force_login(student)
        self.client.post(reverse("start_project"), {"title": "New topic", "description": "", "keywords": ""})
        self.assertEqual(list(Project.objects.get(student=student).milestones.values_list("name", flat=True)), ["Chapter 1"])

        waiting = User.objects.create(username="waiting", role=Role.STUDENT)
        StudentProfile.objects.create(user=waiting, student_number="BU/23A/CS/2002", programme=self.cs_programme)
        self.client.force_login(self.coordinator)
        self.client.post(reverse("supervisor_assignments"), {"student_id": waiting.pk, "supervisor": self.supervisor.pk})
        self.assertEqual(Project.objects.get(student=waiting).milestones.count(), 1)

    def test_changing_or_removing_a_deadline_updates_the_projects(self):
        self.add_deadline()
        deadline = ProjectDeadline.objects.get()
        later = self.due + timedelta(days=7)
        self.client.post(reverse("faculty_deadlines"), {"action": "update", "deadline_id": deadline.pk, "name": "Chapter 1: Introduction", "due_date": later.isoformat()})
        self.assertEqual(set(deadline.milestones.values_list("name", "due_date")), {("Chapter 1: Introduction", later)})

        deadline.milestones.filter(project=self.cs_project).update(done=True)
        self.client.post(reverse("faculty_deadlines"), {"action": "remove", "deadline_id": deadline.pk})
        self.assertFalse(ProjectDeadline.objects.exists())
        self.assertEqual(list(ProjectMilestone.objects.values_list("project_id", "deadline")), [(self.cs_project.pk, None)])

    def test_the_supervisor_adds_marks_done_and_removes_their_own_milestones(self):
        self.add_deadline()
        self.client.force_login(self.supervisor)
        self.client.post(self.milestones_url(), {"action": "add", "name": "Working prototype", "due_date": self.due.isoformat()})
        own = ProjectMilestone.objects.get(name="Working prototype")
        faculty = ProjectMilestone.objects.get(project=self.cs_project, name="Chapter 1")

        self.client.post(self.milestones_url(), {"action": "toggle_done", "milestone_id": faculty.pk})
        faculty.refresh_from_db()
        self.assertTrue(faculty.done)
        self.assertIsNotNone(faculty.done_at)
        self.assertEqual(self.client.post(self.milestones_url(), {"action": "remove", "milestone_id": faculty.pk}).status_code, 403)
        self.client.post(self.milestones_url(), {"action": "remove", "milestone_id": own.pk})
        self.assertFalse(ProjectMilestone.objects.filter(pk=own.pk).exists())

    def test_who_sees_and_who_edits(self):
        student = self.cs_project.student
        cases = ((student, 200, 403), (self.supervisor, 200, 302), (self.coordinator, 200, 403), (self.hod, 200, 403),
                 (self.other_supervisor, 403, 403), (self.cyber_project.student, 403, 403))
        for user, view, edit in cases:
            with self.subTest(user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.milestones_url()).status_code, view)
                response = self.client.post(self.milestones_url(), {"action": "add", "name": "X"})
                self.assertEqual(response.status_code, edit)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("faculty_deadlines")).status_code, 403)

    def test_students_are_reminded_shortly_before_a_due_date(self):
        today = timezone.localdate()
        soon = ProjectMilestone.objects.create(project=self.cs_project, name="Chapter 2", due_date=today + timedelta(days=2))
        ProjectMilestone.objects.create(project=self.cs_project, name="Done already", due_date=today + timedelta(days=1), done=True)
        ProjectMilestone.objects.create(project=self.cs_project, name="Far away", due_date=today + timedelta(days=20))
        tally = flag_deadlines_soon(timezone.now())
        self.assertEqual((tally.flagged, tally.created), (1, 1))
        alert = Notification.objects.get(kind=NotificationKind.DEADLINE_SOON)
        self.assertEqual((alert.recipient, alert.object_id, alert.title), (self.cs_project.student, str(soon.pk), "Chapter 2 is due in 2 days"))
