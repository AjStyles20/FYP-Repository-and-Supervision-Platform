"""The Django admin cannot bypass the workflow: stage, stage dates and archived, and the workflow records."""

from datetime import date
from io import StringIO

from django.contrib import admin
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent

from .models import (
    Project,
    ProjectApprovalDecision,
    ProjectApprovalForm,
    ProjectCompletion,
    ProjectStage,
    ProjectStatusEvent,
    ProjectSupervisorAssignment,
)


class AdminCannotBypassWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Faculty of Computing and Applied Sciences")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        student = User.objects.create(username="amina", first_name="Amina", role=Role.STUDENT)
        StudentProfile.objects.create(user=student, student_number="BU/22/CS/1", programme=cls.programme)
        cls.project = Project.objects.create(
            student=student, title="Attendance tracker", stage=ProjectStage.APPROVED,
            department=cls.department, programme=cls.programme, approval_date=date(2026, 3, 2),
        )
        cls.approval_form = ProjectApprovalForm.objects.create(project=cls.project, proposed_title="Attendance tracker")
        hod = User.objects.create(username="hod", role=Role.HOD, department=cls.department)
        cls.completion = ProjectCompletion.objects.create(project=cls.project, hod=hod, signed_on=date(2026, 7, 1))
        cls.admin_user = User.objects.create_superuser(username="site.admin", password="test-password")

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_project_change_saves_other_fields_but_not_stage_dates_or_archived(self):
        response = self.client.post(reverse("admin:projects_project_change", args=[self.project.pk]), {
            "student": self.project.student_id,
            "title": "Attendance tracker (renamed)",
            "department": self.department.pk,
            "programme": self.programme.pk,
            "stage": ProjectStage.COMPLETED,
            "approval_date": "2020-01-01",
            "submission_date": "2026-05-01",
            "defence_date": "2026-06-01",
            "archived": "on",
            "milestones-TOTAL_FORMS": "0", "milestones-INITIAL_FORMS": "0",
            "documents-TOTAL_FORMS": "0", "documents-INITIAL_FORMS": "0",
            "status_events-TOTAL_FORMS": "0", "status_events-INITIAL_FORMS": "0",
        })

        self.assertRedirects(response, reverse("admin:projects_project_changelist"))
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, "Attendance tracker (renamed)")  # the save went through
        self.assertEqual(self.project.stage, ProjectStage.APPROVED)
        self.assertEqual(
            (self.project.approval_date, self.project.submission_date, self.project.defence_date),
            (date(2026, 3, 2), None, None),
        )
        self.assertFalse(self.project.archived)

    def test_project_add_cannot_set_stage_dates_or_archived(self):
        self.client.post(reverse("admin:projects_project_add"), {
            "student": self.project.student_id,
            "title": "Second topic",
            "department": self.department.pk,
            "programme": self.programme.pk,
            "stage": ProjectStage.COMPLETED,
            "defence_date": "2026-06-01",
            "archived": "on",
            "milestones-TOTAL_FORMS": "0", "milestones-INITIAL_FORMS": "0",
            "documents-TOTAL_FORMS": "0", "documents-INITIAL_FORMS": "0",
            "status_events-TOTAL_FORMS": "0", "status_events-INITIAL_FORMS": "0",
        })

        created = Project.objects.get(title="Second topic")
        self.assertEqual((created.stage, created.defence_date, created.archived), (ProjectStage.PROPOSED, None, False))

    def test_approval_form_and_completion_cannot_be_added_changed_or_deleted(self):
        for record, name in ((self.approval_form, "projectapprovalform"), (self.completion, "projectcompletion")):
            with self.subTest(name):
                add = self.client.post(reverse(f"admin:projects_{name}_add"), {"project": self.project.pk})
                change = self.client.post(reverse(f"admin:projects_{name}_change", args=[record.pk]), {})
                delete = self.client.post(reverse(f"admin:projects_{name}_delete", args=[record.pk]), {"post": "yes"})
                bulk = self.client.post(reverse(f"admin:projects_{name}_changelist"),
                                        {"action": "delete_selected", "_selected_action": [record.pk], "post": "yes"})

                self.assertEqual((add.status_code, change.status_code, delete.status_code), (403, 403, 403))
                self.assertNotEqual(bulk.status_code, 500)
                self.assertTrue(type(record).objects.filter(pk=record.pk).exists())
                self.assertEqual(self.client.get(reverse(f"admin:projects_{name}_change", args=[record.pk])).status_code, 200)

        self.approval_form.refresh_from_db()
        self.completion.refresh_from_db()
        self.assertEqual(self.approval_form.proposed_title, "Attendance tracker")
        self.assertEqual(self.completion.signed_on, date(2026, 7, 1))

    def test_project_cannot_be_deleted_in_the_admin_one_at_a_time_or_in_bulk(self):
        ProjectStatusEvent.objects.create(project=self.project, to_stage=ProjectStage.APPROVED, actor=self.admin_user)

        delete = self.client.post(reverse("admin:projects_project_delete", args=[self.project.pk]), {"post": "yes"})
        bulk = self.client.post(reverse("admin:projects_project_changelist"),
                                {"action": "delete_selected", "_selected_action": [self.project.pk], "post": "yes"})

        self.assertEqual(delete.status_code, 403)
        self.assertNotEqual(bulk.status_code, 500)
        self.assertNotIn("delete_selected", admin.site._registry[Project].get_actions(delete.wsgi_request))
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.assertEqual(self.project.status_events.count(), 1)
        self.assertTrue(ProjectCompletion.objects.filter(pk=self.completion.pk).exists())

    def test_purge_demo_still_deletes_demo_projects(self):
        Project.objects.filter(pk=self.project.pk).update(is_demo=True)
        ProjectStatusEvent.objects.create(project=self.project, to_stage=ProjectStage.APPROVED)

        call_command("purge_demo", stdout=StringIO())

        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(ProjectStatusEvent.objects.filter(project_id=self.project.pk).exists())

    def test_every_workflow_record_is_view_only_in_the_admin(self):
        request = self.client.get(reverse("admin:index")).wsgi_request
        for model in (ProjectStatusEvent, ProjectSupervisorAssignment, ProjectApprovalDecision,
                      ProjectApprovalForm, ProjectCompletion, AuditEvent):
            model_admin = admin.site._registry[model]
            with self.subTest(model.__name__):
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request))
                self.assertFalse(model_admin.has_delete_permission(request))
                self.assertTrue(model_admin.has_view_permission(request))
