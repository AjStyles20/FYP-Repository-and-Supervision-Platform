"""The student's proposal: only the fields the supervisor needs, drafts, and editing until a decision (D-36)."""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, SupervisorProfile, User
from apps.supervision.models import Notification, NotificationKind

from .models import Project, ProjectApprovalForm, ProjectStage
from .services import record_supervisor_decision

BASE = {"proposed_title": "Library Seat Booking", "problem_statement": "Seats are hard to find.",
        "objectives": "Book seats online.", "methodology": "Prototype and survey.", "tools_and_technologies": "Django"}


class ProposalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Computing")
        department = Department.objects.create(faculty=faculty, name="Computer Science")
        programme = Programme.objects.create(department=department, name="Computer Science", degree_type="BSc")
        cls.topic_only = User.objects.create(username="danjuma", role=Role.SUPERVISOR, department=department)
        SupervisorProfile.objects.create(user=cls.topic_only, approval_method="topic_only")
        cls.literature = User.objects.create(username="okoro", role=Role.SUPERVISOR, department=department)
        SupervisorProfile.objects.create(user=cls.literature, approval_method="literature_review")
        cls.student = User.objects.create(username="ada", first_name="Ada", last_name="Bello", role=Role.STUDENT)
        StudentProfile.objects.create(user=cls.student, student_number="BU/22A/CS/1001", programme=programme)
        cls.project = Project.objects.create(student=cls.student, title="Topic to be agreed", stage=ProjectStage.PROPOSED,
                                             department=department, programme=programme, supervisor=cls.topic_only)
        cls.url = reverse("project_workflow", args=[cls.project.pk])

    def post(self, action, **data):
        self.client.force_login(self.student)
        return self.client.post(self.url, {"action": action, **data})

    def use(self, supervisor):
        Project.objects.filter(pk=self.project.pk).update(supervisor=supervisor)
        self.project.refresh_from_db()

    def test_a_topic_only_supervisor_gets_a_short_form(self):
        self.client.force_login(self.student)
        fields = set(self.client.get(self.url).context["form"].fields)
        self.assertEqual(fields, {"proposed_title", "problem_statement", "objectives", "methodology", "tools_and_technologies"})

    def test_a_literature_review_is_asked_for_kept_and_lets_the_supervisor_decide(self):
        self.use(self.literature)
        self.assertContains(self.post("submit", **BASE), "This field is required")  # review and gap now required
        self.post("submit", **BASE, literature_review="Ten sources compared.", research_gap="No offline booking.")
        form = ProjectApprovalForm.objects.get(project=self.project)
        self.assertEqual((form.literature_review, form.research_gap), ("Ten sources compared.", "No offline booking."))
        record_supervisor_decision(self.project, supervisor=self.literature, decision="accepted", comments="",
                                   name_on_form="Dr Okoro", signed_on=timezone.localdate())
        self.project.refresh_from_db()
        self.assertEqual(self.project.stage, ProjectStage.SUPERVISOR_ACCEPTED)

    def test_a_draft_needs_only_a_title_and_stays_with_the_student(self):
        self.assertRedirects(self.post("draft", proposed_title="Seat booking (draft)"), self.url)
        form = ProjectApprovalForm.objects.get(project=self.project)
        self.assertIsNone(form.student_signed_on)
        self.assertEqual(form.state_label, "Draft")
        self.assertFalse(Notification.objects.filter(kind=NotificationKind.PROPOSAL_SUBMITTED).exists())
        with self.assertRaisesMessage(Exception, "still a draft"):
            record_supervisor_decision(self.project, supervisor=self.topic_only, decision="accepted", comments="",
                                       name_on_form="Mr Danjuma", signed_on=timezone.localdate())
        self.client.force_login(self.topic_only)
        self.assertEqual(self.client.get(reverse("dashboard")).context["proposal_count"], 0)

    def test_submitting_dates_the_form_and_alerts_the_supervisor(self):
        self.post("submit", **BASE)
        form = ProjectApprovalForm.objects.get(project=self.project)
        self.assertEqual((form.student_signed_on, form.student_name_on_form), (timezone.localdate(), "Ada Bello"))
        self.assertEqual(Notification.objects.get(kind=NotificationKind.PROPOSAL_SUBMITTED).recipient, self.topic_only)
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, "Library Seat Booking")

    def test_coming_back_opens_the_saved_proposal_and_it_stays_editable_until_a_decision(self):
        self.post("draft", proposed_title="Seat booking", objectives="Half-written objectives")
        self.client.force_login(self.student)
        initial = self.client.get(self.url).context["form"].initial
        self.assertEqual((initial["proposed_title"], initial["objectives"]), ("Seat booking", "Half-written objectives"))

        self.post("submit", **BASE)
        self.post("submit", **{**BASE, "objectives": "Book and release seats online."})  # still editable
        self.assertEqual(ProjectApprovalForm.objects.get(project=self.project).objectives, "Book and release seats online.")

        record_supervisor_decision(self.project, supervisor=self.topic_only, decision="accepted", comments="",
                                   name_on_form="Mr Danjuma", signed_on=timezone.localdate())
        self.client.force_login(self.student)
        self.assertIsNone(self.client.get(self.url).context["form"])  # accepted: the topic is now the record
