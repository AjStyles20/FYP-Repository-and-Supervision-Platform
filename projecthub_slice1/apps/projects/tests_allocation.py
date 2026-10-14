"""The coordinator allocates supervisors to students who have no project yet, keeping the numbers even."""

from django.test import TestCase
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent

from .models import Project, ProjectStage
from .services import submit_proposal
from .services.assignment import TOPIC_TO_BE_AGREED


class StudentAllocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Allocation Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.cyber = Department.objects.create(faculty=faculty, name="Cyber Security")
        law = Department.objects.create(faculty=Faculty.objects.create(name="Faculty of Law"), name="Private Law")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.cyber_programme = Programme.objects.create(department=cls.cyber, name="Cyber Security", degree_type="BSc")
        other_programme = Programme.objects.create(department=law, name="Law", degree_type="LLB")
        cls.coordinator = User.objects.create(username="coord", first_name="Babatunde", last_name="Jimoh",
                                              role=Role.COORDINATOR, department=cls.department, can_assign_supervisors=True)
        cls.julius = User.objects.create(username="julius", first_name="Julius", last_name="Makinde",
                                         role=Role.SUPERVISOR, department=cls.department)
        cls.esther = User.objects.create(username="esther", first_name="Esther", last_name="Omonayin",
                                         role=Role.SUPERVISOR, department=cls.department)

        def student(username, programme=None, **profile):
            user = User.objects.create(username=username, first_name=username.title(), role=Role.STUDENT)
            StudentProfile.objects.create(user=user, student_number=f"BU/23A/CS/{1000 + User.objects.count()}",
                                          programme=programme or cls.programme, **profile)
            return user

        cls.tolu = student("tolu")
        cls.ada = student("ada")
        cls.pending = student("pending", registration_status=StudentProfile.RegistrationStatus.PENDING)
        cls.finished = student("finished", student_status=StudentProfile.Status.FYP_COMPLETED)
        cls.elsewhere = student("elsewhere", programme=other_programme)
        cls.started = student("started")
        cls.busy_project = Project.objects.create(student=cls.started, title="Seat booking", department=cls.department,
                                                  programme=cls.programme, supervisor=cls.julius)

    def setUp(self):
        self.client.force_login(self.coordinator)

    def page(self):
        return self.client.get(reverse("supervisor_assignments"))

    def test_students_without_a_project_wait_for_a_supervisor(self):
        waiting = [row["student"] for row in self.page().context["student_rows"]]
        self.assertEqual(waiting, [self.ada, self.tolu])  # not pending, finished, other department or already started

    def test_supervisors_are_listed_least_busy_first_with_their_load(self):
        page = self.page()
        self.assertContains(page, "Esther Omonayin (0 active)")
        self.assertContains(page, "Julius Makinde (1 active)")
        choices = [label for _, label in page.context["student_rows"][0]["form"].fields["supervisor"].choices][1:]
        self.assertEqual(choices[-1], "Julius Makinde (1 active)")

    def test_assigning_a_waiting_student_creates_their_project_with_history(self):
        response = self.client.post(reverse("supervisor_assignments"),
                                    {"student_id": self.tolu.pk, "supervisor": self.esther.pk, "reason": ""})
        self.assertRedirects(response, reverse("supervisor_assignments"))
        project = Project.objects.get(student=self.tolu)
        self.assertEqual((project.title, project.stage, project.supervisor, project.department),
                         (TOPIC_TO_BE_AGREED, ProjectStage.PROPOSED, self.esther, self.department))
        assignment = project.supervisor_assignments.get()
        self.assertEqual((assignment.supervisor, assignment.assigned_by), (self.esther, self.coordinator))
        self.assertEqual(project.status_events.get().actor, self.coordinator)
        self.assertEqual(set(AuditEvent.objects.values_list("action", flat=True)),
                         {"project.created", "project.supervisor_assigned"})
        page = self.page()
        self.assertNotIn(self.tolu, [row["student"] for row in page.context["student_rows"]])
        self.assertIn(project, [row["project"] for row in page.context["rows"]])

    def test_the_coordinator_can_supervise_the_student_themself(self):
        self.client.post(reverse("supervisor_assignments"), {"student_id": self.ada.pk, "supervisor": self.coordinator.pk})
        self.assertEqual(Project.objects.get(student=self.ada).supervisor, self.coordinator)

    def test_changing_a_supervisor_needs_a_reason(self):
        url = reverse("supervisor_assignments")
        response = self.client.post(url, {"project_id": self.busy_project.pk, "supervisor": self.esther.pk, "reason": " "})
        self.assertContains(response, "Say why the supervisor is changing")
        self.busy_project.refresh_from_db()
        self.assertEqual(self.busy_project.supervisor, self.julius)

        self.client.post(url, {"project_id": self.busy_project.pk, "supervisor": self.esther.pk,
                               "reason": "Student asked: wants a supervisor in artificial intelligence"})
        self.busy_project.refresh_from_db()
        self.assertEqual(self.busy_project.supervisor, self.esther)
        self.assertEqual(self.busy_project.supervisor_assignments.get(ended_at__isnull=True).change_reason,
                         "Student asked: wants a supervisor in artificial intelligence")

    def test_a_coordinator_works_across_the_faculty_whatever_their_own_field(self):
        cyber_coordinator = User.objects.create(username="cyber.coord", role=Role.COORDINATOR, department=self.cyber,
                                                can_assign_supervisors=True)
        cyber_student = User.objects.create(username="kemi", role=Role.STUDENT)
        StudentProfile.objects.create(user=cyber_student, student_number="BU/23A/CY/2001", programme=self.cyber_programme)
        self.client.force_login(cyber_coordinator)
        page = self.client.get(reverse("supervisor_assignments"))
        self.assertEqual({row["student"] for row in page.context["student_rows"]}, {self.ada, self.tolu, cyber_student})
        self.assertIn(self.busy_project, [row["project"] for row in page.context["rows"]])

        # A Computer Science supervisor for a Cyber Security student, and a change on a CS project.
        self.client.post(reverse("supervisor_assignments"), {"student_id": cyber_student.pk, "supervisor": self.esther.pk})
        self.assertEqual(Project.objects.get(student=cyber_student).supervisor, self.esther)
        self.client.post(reverse("supervisor_assignments"), {"project_id": self.busy_project.pk, "supervisor": cyber_coordinator.pk,
                                                             "reason": "Student asked the coordinator to supervise"})
        self.busy_project.refresh_from_db()
        self.assertEqual(self.busy_project.supervisor, cyber_coordinator)

    def test_a_delegated_hod_stays_within_their_department(self):
        hod = User.objects.create(username="cyber.hod", role=Role.HOD, department=self.cyber, can_assign_supervisors=True)
        self.client.force_login(hod)
        page = self.client.get(reverse("supervisor_assignments"))
        self.assertEqual(list(page.context["student_rows"]), [])
        self.assertEqual(list(page.context["rows"]), [])

    def test_students_outside_the_faculty_cannot_be_allocated(self):
        response = self.client.post(reverse("supervisor_assignments"), {"student_id": self.elsewhere.pk, "supervisor": self.esther.pk})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Project.objects.filter(student=self.elsewhere).exists())

    def test_the_students_proposal_replaces_the_placeholder_title(self):
        self.client.post(reverse("supervisor_assignments"), {"student_id": self.tolu.pk, "supervisor": self.esther.pk})
        project = Project.objects.get(student=self.tolu)
        submit_proposal(project, proposed_title="Library Seat Booking System", problem_statement="Seats are hard to find.",
                        objectives="Book seats online.", methodology="Prototype and survey.", tools_and_technologies="Django")
        project.refresh_from_db()
        self.assertEqual(project.title, "Library Seat Booking System")
