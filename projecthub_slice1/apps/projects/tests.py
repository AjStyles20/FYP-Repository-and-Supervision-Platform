import tempfile
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent
from apps.supervision.models import Announcement

from .models import (
    ApprovalDecisionStep,
    ArchivedProject,
    Project,
    ProjectApprovalDecision,
    ProjectApprovalForm,
    ProjectCompletion,
    ProjectDocument,
    ProjectStage,
    ProjectStatusEvent,
    ProjectSupervisorAssignment,
    SupervisorDecision,
)
from .services import (
    assign_project_supervisor,
    available_years,
    log_approved_form,
    record_supervisor_decision,
    sign_off_completion,
    submit_proposal,
    unassign_project_supervisor,
)


class RepositoryTests(TestCase):
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
        faculty = Faculty.objects.create(name="Computing Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.programme = Programme.objects.create(
            department=cls.department,
            name="Computer Science",
            degree_type="BSc",
        )
        cls.student = User.objects.create_user(
            username="repository.student@bazeuniversity.edu.ng",
            email="repository.student@bazeuniversity.edu.ng",
            password="test-password",
            first_name="Ada",
            last_name="Student",
            role=Role.STUDENT,
        )
        cls.profile = StudentProfile.objects.create(
            user=cls.student,
            student_number="BU/26/CS/1234",
            programme=cls.programme,
            contact_email="ada.contact@example.com",
            contact_consent=True,
            graduation_year=2026,
        )
        cls.alumni = User.objects.create_user(
            username="repository.alumni@bazeuniversity.edu.ng",
            email="repository.alumni@bazeuniversity.edu.ng",
            password="test-password",
            first_name="Grace",
            last_name="Alumni",
            role=Role.STUDENT,
        )
        StudentProfile.objects.create(
            user=cls.alumni,
            student_number="BU/25/CS/4321",
            programme=cls.programme,
            student_status=StudentProfile.Status.GRADUATED,
            graduation_year=2025,
            contact_email="grace.contact@example.com",
            contact_consent=True,
        )
        cls.supervisor = User.objects.create_user(
            username="supervisor.okoro",
            email="okoro@bazeuniversity.edu.ng",
            password="test-password",
            first_name="A",
            last_name="Okoro",
            role=Role.SUPERVISOR,
            department=cls.department,
        )
        cls.next_supervisor = User.objects.create(
            username="supervisor.yusuf",
            first_name="B",
            last_name="Yusuf",
            role=Role.SUPERVISOR,
            department=cls.department,
        )
        cls.coordinator = User.objects.create(
            username="department.coordinator",
            role=Role.COORDINATOR,
            department=cls.department,
            can_assign_supervisors=True,
        )
        cls.hod = User.objects.create(
            username="department.hod",
            role=Role.HOD,
            department=cls.department,
        )
        cls.admin = User.objects.create(username="system.admin", role=Role.ADMIN)
        cls.current_project = Project.objects.create(
            student=cls.student,
            title="Campus Transport Analytics",
            description="A study of transport patterns across campus.",
            department=cls.department,
            programme=cls.programme,
            supervisor=cls.supervisor,
            stage=ProjectStage.IN_PROGRESS,
            is_demo=True,
        )
        cls.past_project = ArchivedProject.objects.create(
            title="Student Support Portal",
            description="An archived student support platform.",
            year=2025,
            department=cls.department,
            programme=cls.programme,
            student=cls.alumni,
            supervisor=cls.supervisor,
            gap_summary="Evaluate accessibility with a larger student sample.",
        )
        cls.past_project.previous_supervisors.add(
            User.objects.create_user(
                username="previous.supervisor",
                password="test-password",
                first_name="B",
                last_name="Earlier",
                role=Role.SUPERVISOR,
            )
        )

    def test_repository_requires_authentication(self):
        response = self.client.get(reverse("repository"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('repository')}")

    def test_my_project_is_student_only(self):
        self.client.force_login(self.coordinator)

        response = self.client.get(reverse("my_project"))

        self.assertEqual(response.status_code, 403)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertNotContains(dashboard, "My project")

    def test_supervision_history_shows_only_assigned_and_archived_projects(self):
        self.past_project.previous_supervisors.add(self.coordinator)
        reassigned_project = Project.objects.create(
            student=self.student,
            title="Former coordinator supervisee",
            description="Summary of a project once assigned to this coordinator.",
            department=self.department,
            programme=self.programme,
            supervisor=self.next_supervisor,
        )
        ProjectSupervisorAssignment.objects.create(
            project=reassigned_project,
            supervisor=self.coordinator,
            assigned_by=self.coordinator,
            ended_at=reassigned_project.updated_at,
            change_reason="Reassigned to a subject specialist.",
        )
        self.client.force_login(self.coordinator)

        response = self.client.get(reverse("supervision"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Former coordinator supervisee")
        self.assertContains(response, "Student Support Portal")
        self.assertNotContains(response, "Campus Transport Analytics")
        self.assertNotContains(response, "Assign supervisor")

    def test_supervisor_can_add_and_remove_a_student_without_deleting_their_record(self):
        new_student = User.objects.create_user(
            username="new.supervisee", password="test-password", first_name="New", last_name="Student",
            role=Role.STUDENT,
        )
        StudentProfile.objects.create(user=new_student, student_number="BU/26/CS/8899", programme=self.programme)
        unassigned_project = Project.objects.create(
            student=new_student, title="Unassigned topic", department=self.department, programme=self.programme,
        )
        self.client.force_login(self.supervisor)

        added = self.client.post(reverse("supervision"), {
            "action": "add_student", "project": unassigned_project.pk, "reason": "Research area match",
        })

        self.assertRedirects(added, reverse("supervision"))
        unassigned_project.refresh_from_db()
        self.assertEqual(unassigned_project.supervisor, self.supervisor)
        self.assertTrue(unassigned_project.supervisor_assignments.filter(ended_at__isnull=True).exists())
        self.assertTrue(Announcement.objects.filter(project=unassigned_project, title="You have a new supervisor").exists())

        removed = self.client.post(reverse("supervision"), {
            "action": "remove_student", "project_id": unassigned_project.pk, "reason": "Reassign to another specialist",
        })

        self.assertRedirects(removed, reverse("supervision"))
        unassigned_project.refresh_from_db()
        self.assertIsNone(unassigned_project.supervisor)
        self.assertTrue(unassigned_project.supervisor_assignments.filter(ended_at__isnull=False).exists())
        self.assertTrue(Announcement.objects.filter(project=unassigned_project, title="Supervisor assignment updated").exists())

    def test_supervisor_can_edit_project_details_with_audit_and_student_notice(self):
        editable_project = Project.objects.create(
            student=self.student, title="Editable topic", description="Old summary", department=self.department,
            programme=self.programme, supervisor=self.supervisor, is_demo=False,
        )
        self.client.force_login(self.supervisor)

        response = self.client.post(reverse("supervision"), {
            "action": "edit_project", "project_id": editable_project.pk,
            "title": "Updated campus transport study", "description": "Expanded summary", "keywords": "transit, analytics",
        })

        self.assertRedirects(response, reverse("supervision"))
        editable_project.refresh_from_db()
        self.assertEqual(editable_project.title, "Updated campus transport study")
        self.assertTrue(AuditEvent.objects.filter(action="project.supervisor_edited", object_id=str(editable_project.pk)).exists())
        self.assertTrue(Announcement.objects.filter(project=editable_project, title="Your project topic was updated").exists())

    def test_supervision_and_approval_pages_render_project_links(self):
        self.client.force_login(self.coordinator)
        self.assertEqual(self.client.get(reverse("supervision")).status_code, 200)

        self.current_project.stage = ProjectStage.PROPOSED
        self.current_project.save(update_fields=["stage"])
        response = self.client.get(reverse("approvals"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("current_project_detail", args=[self.current_project.pk]))

    def test_repository_only_shows_completed_graduated_projects(self):
        self.client.force_login(self.student)

        repository_response = self.client.get(reverse("repository"))
        running_response = self.client.get(reverse("running_topics"))

        self.assertContains(repository_response, "Student Support Portal")
        self.assertNotContains(repository_response, "Campus Transport Analytics")
        self.assertContains(running_response, "Campus Transport Analytics")
        self.assertNotContains(running_response, "Student Support Portal")
        self.assertContains(repository_response, "Completed project repository")
        self.assertContains(running_response, "Explore running topics")

    def test_repository_hides_archived_work_until_graduation_is_verified(self):
        unverified_project = ArchivedProject.objects.create(
            title="Awaiting verified graduation",
            year=2026,
            department=self.department,
            programme=self.programme,
            student=self.student,
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("repository"))

        self.assertNotContains(response, unverified_project.title)

    def test_completed_project_detail_requires_graduated_student(self):
        self.client.force_login(self.student)
        unverified_project = ArchivedProject.objects.create(
            title="Not yet eligible",
            year=2026,
            department=self.department,
            programme=self.programme,
            student=self.student,
        )

        response = self.client.get(reverse("past_project_detail", args=[unverified_project.pk]))

        self.assertEqual(response.status_code, 404)

    def test_repository_searches_topics_students_and_supervisors(self):
        self.client.force_login(self.student)

        for search_term in ("Transport Analytics", "Ada", "Okoro"):
            with self.subTest(search_term=search_term):
                response = self.client.get(reverse("running_topics"), {"q": search_term})
                self.assertContains(response, "Campus Transport Analytics")

    def test_student_id_search_is_not_available_to_students(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("running_topics"), {"q": "BU/26/CS/1234"})

        self.assertNotContains(response, "Campus Transport Analytics")
        self.assertNotContains(response, "student ID")

    def test_staff_can_search_by_student_id(self):
        staff = User.objects.create_user(
            username="review.coordinator",
            password="test-password",
            role=Role.COORDINATOR,
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("running_topics"), {"q": "BU/26/CS/1234"})

        self.assertContains(response, "Campus Transport Analytics")

    def test_current_project_detail_hides_id_and_only_shows_consented_contact(self):
        self.client.force_login(User.objects.create_user(username="reader", role=Role.STUDENT))

        response = self.client.get(
            reverse("current_project_detail", args=[self.current_project.pk])
        )

        self.assertContains(response, "Campus Transport Analytics")
        self.assertContains(response, "ada.contact@example.com")
        self.assertNotContains(response, "BU/26/CS/1234")
        self.assertNotContains(response, "corrective_action")

    def test_staff_can_see_student_id_on_project_detail(self):
        staff = User.objects.create_user(username="detail.staff", role=Role.SUPERVISOR)
        self.client.force_login(staff)

        response = self.client.get(
            reverse("current_project_detail", args=[self.current_project.pk])
        )

        self.assertContains(response, "BU/26/CS/1234")

    def test_past_project_detail_shows_gap_and_separates_graduation_year(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("past_project_detail", args=[self.past_project.pk]))

        self.assertContains(response, "Evaluate accessibility")
        self.assertContains(response, "Verified graduation year")
        self.assertContains(response, "2025")
        self.assertContains(response, "Archive year 2025")
        self.assertContains(response, "Earlier supervisor")
        self.assertContains(response, "B Earlier")

    def test_filters_apply_to_both_repository_sections(self):
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("repository"),
            {"department": self.department.pk},
        )

        self.assertContains(response, "Student Support Portal")

    def test_repository_years_use_local_time_without_mysql_time_zone_tables(self):
        # 23:30 UTC on 31 December is already 00:30 on 1 January in Lagos (UTC+1).
        # The year list is worked out in Python so it works on MySQL without time zone
        # tables, and it must agree with the year filter and the year shown on the card.
        late_utc = datetime(2026, 12, 31, 23, 30, tzinfo=dt_timezone.utc)
        Project.objects.filter(pk=self.current_project.pk).update(updated_at=late_utc)

        self.assertEqual(available_years(), [2027, 2025])

        self.client.force_login(self.student)
        response = self.client.get(reverse("running_topics"), {"year": "2027"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["years"], [2027, 2025])
        cards = response.context["items"]
        self.assertEqual([card["project"].title for card in cards], ["Campus Transport Analytics"])
        self.assertEqual(cards[0]["year"], 2027)

        response = self.client.get(reverse("running_topics"), {"year": "2026"})
        self.assertEqual(response.context["items"], [])

    def test_archived_projects_are_not_listed_as_current(self):
        self.current_project.archived = True
        self.current_project.save(update_fields=["archived"])
        self.client.force_login(self.student)

        response = self.client.get(reverse("running_topics"))

        self.assertNotContains(response, "Campus Transport Analytics")

    def test_past_project_shows_shared_documents_only(self):
        shared = ProjectDocument.objects.create(
            archived_project=self.past_project,
            title="Public abstract",
            file=SimpleUploadedFile("abstract.pdf", b"public abstract"),
            visibility=ProjectDocument.Visibility.BAZE_USERS,
        )
        staff_only = ProjectDocument.objects.create(
            archived_project=self.past_project,
            title="Staff assessment",
            file=SimpleUploadedFile("assessment.pdf", b"staff assessment"),
            visibility=ProjectDocument.Visibility.STAFF_ONLY,
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("past_project_detail", args=[self.past_project.pk]))

        self.assertContains(response, "Public abstract")
        self.assertNotContains(response, "Staff assessment")
        self.assertContains(response, reverse("download_project_document", args=[shared.pk]))
        self.assertNotContains(response, reverse("download_project_document", args=[staff_only.pk]))

    def test_staff_only_document_download_is_denied_to_students(self):
        document = ProjectDocument.objects.create(
            archived_project=self.past_project,
            title="Staff assessment",
            file=SimpleUploadedFile("assessment.pdf", b"staff assessment"),
            visibility=ProjectDocument.Visibility.STAFF_ONLY,
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("download_project_document", args=[document.pk]))

        self.assertEqual(response.status_code, 403)

    def test_signed_in_baze_user_can_download_shared_document(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            document = ProjectDocument.objects.create(
                archived_project=self.past_project,
                title="Public abstract",
                file=SimpleUploadedFile("abstract.pdf", b"public abstract"),
                visibility=ProjectDocument.Visibility.BAZE_USERS,
            )
            self.client.force_login(self.student)

            response = self.client.get(reverse("download_project_document", args=[document.pk]))

            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"public abstract")
            self.assertIn("abstract.pdf", response["Content-Disposition"])

    def test_coordinator_can_assign_and_reassign_supervisor_with_history(self):
        self.client.force_login(self.coordinator)

        response = self.client.post(
            reverse("supervisor_assignments"),
            {
                "project_id": self.current_project.pk,
                "supervisor": self.next_supervisor.pk,
                "reason": "Supervisor workload balancing",
            },
        )

        self.assertRedirects(response, reverse("supervisor_assignments"))
        self.current_project.refresh_from_db()
        self.assertEqual(self.current_project.supervisor, self.next_supervisor)
        assignments = list(self.current_project.supervisor_assignments.order_by("assigned_at"))
        self.assertEqual(len(assignments), 2)
        self.assertEqual(assignments[0].supervisor, self.supervisor)
        self.assertIsNotNone(assignments[0].ended_at)
        self.assertEqual(assignments[1].supervisor, self.next_supervisor)
        self.assertIsNone(assignments[1].ended_at)
        self.assertEqual(assignments[1].assigned_by, self.coordinator)
        self.assertEqual(assignments[1].change_reason, "Supervisor workload balancing")

    def test_assignment_page_is_restricted_to_department_staff(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("supervisor_assignments")).status_code, 403)

        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("supervisor_assignments")).status_code, 403)

        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("supervisor_assignments"))
        self.assertContains(response, "Student allocation")
        self.assertContains(response, self.current_project.title)

        for staff_user in (self.hod, self.admin):
            with self.subTest(role=staff_user.role):
                self.client.force_login(staff_user)
                self.assertEqual(self.client.get(reverse("supervisor_assignments")).status_code, 403)

    def test_supervisor_or_hod_can_be_delegated_assignment_authority(self):
        self.hod.can_assign_supervisors = True
        self.hod.save(update_fields=["can_assign_supervisors"])
        self.client.force_login(self.hod)

        response = self.client.get(reverse("supervisor_assignments"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.current_project.title)

    def test_coordinator_cannot_assign_supervisor_from_another_department(self):
        other_faculty = Faculty.objects.create(name="Other Faculty")
        other_department = Department.objects.create(faculty=other_faculty, name="Other Department")
        outside_supervisor = User.objects.create(
            username="outside.supervisor",
            role=Role.SUPERVISOR,
            department=other_department,
        )
        self.client.force_login(self.coordinator)

        response = self.client.post(
            reverse("supervisor_assignments"),
            {
                "project_id": self.current_project.pk,
                "supervisor": outside_supervisor.pk,
                "reason": "Cross-department assignment",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.current_project.refresh_from_db()
        self.assertEqual(self.current_project.supervisor, self.supervisor)
        self.assertFalse(self.current_project.supervisor_assignments.exists())


def _assignment_fixtures(suffix=""):
    """A department, two supervisors and a student project, for the assignment constraint tests."""
    faculty = Faculty.objects.create(name=f"Assignment Faculty{suffix}")
    department = Department.objects.create(faculty=faculty, name=f"Assignment Department{suffix}")
    programme = Programme.objects.create(department=department, name="Software Engineering", degree_type="BSc")
    student = User.objects.create(username=f"assign.student{suffix}", role=Role.STUDENT)
    first = User.objects.create(username=f"assign.first{suffix}", role=Role.SUPERVISOR, department=department)
    second = User.objects.create(username=f"assign.second{suffix}", role=Role.SUPERVISOR, department=department)
    project = Project.objects.create(
        student=student, title=f"Assignment project{suffix}", department=department, programme=programme
    )
    return project, first, second


class SupervisorAssignmentConstraintTests(TestCase):
    """One current supervisor per project, enforced by the database on SQLite and MySQL."""

    @classmethod
    def setUpTestData(cls):
        cls.project, cls.first, cls.second = _assignment_fixtures()

    def test_second_current_supervisor_is_rejected_by_the_database(self):
        ProjectSupervisorAssignment.objects.create(project=self.project, supervisor=self.first)

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectSupervisorAssignment.objects.create(project=self.project, supervisor=self.second)

        self.assertEqual(self.project.supervisor_assignments.count(), 1)

    def test_bulk_create_cannot_bypass_the_rule(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectSupervisorAssignment.objects.bulk_create([
                ProjectSupervisorAssignment(project=self.project, supervisor=self.first),
                ProjectSupervisorAssignment(project=self.project, supervisor=self.second),
            ])

    def test_ended_rows_are_not_current_and_do_not_clash(self):
        now = timezone.now()
        for supervisor in (self.first, self.second, self.first):
            ProjectSupervisorAssignment.objects.create(project=self.project, supervisor=supervisor, ended_at=now)
        current = ProjectSupervisorAssignment.objects.create(project=self.project, supervisor=self.second)

        self.assertEqual(list(self.project.supervisor_assignments.filter(is_current=True)), [current])
        self.assertEqual(self.project.supervisor_assignments.filter(is_current__isnull=True).count(), 3)

    def test_ending_through_save_with_update_fields_clears_is_current(self):
        assignment = ProjectSupervisorAssignment.objects.create(project=self.project, supervisor=self.first)
        assignment.ended_at = timezone.now()
        assignment.save(update_fields=["ended_at"])

        assignment.refresh_from_db()
        self.assertIsNone(assignment.is_current)
        ProjectSupervisorAssignment.objects.create(project=self.project, supervisor=self.second)

    def test_queryset_update_of_ended_at_clears_is_current(self):
        assignment = ProjectSupervisorAssignment.objects.create(project=self.project, supervisor=self.first)

        ProjectSupervisorAssignment.objects.filter(pk=assignment.pk).update(ended_at=timezone.now())

        assignment.refresh_from_db()
        self.assertIsNone(assignment.is_current)
        ProjectSupervisorAssignment.objects.create(project=self.project, supervisor=self.second)

    def test_database_rejects_is_current_out_of_step_with_ended_at(self):
        assignment = ProjectSupervisorAssignment.objects.create(
            project=self.project, supervisor=self.first, ended_at=timezone.now()
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectSupervisorAssignment.objects.filter(pk=assignment.pk).update(is_current=True)

    def test_reassignment_service_keeps_exactly_one_current_row(self):
        assign_project_supervisor(self.project.pk, self.first, assigned_by=None)
        assign_project_supervisor(self.project.pk, self.second, assigned_by=None, change_reason="Workload")
        unassign_project_supervisor(self.project.pk, supervisor=self.second, changed_by=None)
        assign_project_supervisor(self.project.pk, self.first, assigned_by=None)

        rows = list(self.project.supervisor_assignments.order_by("assigned_at", "id"))
        self.assertEqual([row.is_current for row in rows], [None, None, True])
        self.assertEqual([row.ended_at is None for row in rows], [False, False, True])


class SupervisorAssignmentMigrationTests(TransactionTestCase):
    """Migration 0010 on a database that already holds assignment rows, current and ended.

    Migrations change the schema, which MySQL cannot roll back inside a transaction, so this
    needs TransactionTestCase. It writes no audit events, so the table flush afterwards is safe.
    """

    before = [("projects", "0009_projectapprovalform_approval_criteria_snapshot")]

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.before)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_existing_rows_are_converted_and_the_constraint_added(self):
        old_apps = self.executor.loader.project_state(self.before).apps
        OldAssignment = old_apps.get_model("projects", "ProjectSupervisorAssignment")
        reassigned, first, second = _assignment_fixtures(" A")
        unassigned, third, _ = _assignment_fixtures(" B")
        earlier, later = timezone.now() - timedelta(days=30), timezone.now() - timedelta(days=10)

        ended = OldAssignment.objects.create(
            project_id=reassigned.pk, supervisor_id=first.pk, assigned_at=earlier, ended_at=later
        )
        kept = OldAssignment.objects.create(project_id=reassigned.pk, supervisor_id=second.pk, assigned_at=later)
        OldAssignment.objects.create(project_id=unassigned.pk, supervisor_id=third.pk, assigned_at=earlier, ended_at=later)
        duplicate_open = newest_open = None
        if not connection.features.supports_partial_indexes:
            # MySQL never enforced the old conditional rule, so two open rows may already exist.
            duplicate_open = OldAssignment.objects.create(
                project_id=unassigned.pk, supervisor_id=first.pk, assigned_at=earlier
            )
            newest_open = OldAssignment.objects.create(
                project_id=unassigned.pk, supervisor_id=second.pk, assigned_at=later
            )

        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

        rows = {row.pk: row for row in ProjectSupervisorAssignment.objects.all()}
        self.assertIs(rows[kept.pk].is_current, True)
        self.assertIsNone(rows[ended.pk].is_current)
        if duplicate_open is None:
            self.assertFalse(ProjectSupervisorAssignment.objects.filter(project=unassigned, is_current=True).exists())
        else:
            self.assertIsNone(rows[duplicate_open.pk].is_current)
            self.assertEqual(rows[duplicate_open.pk].ended_at, rows[newest_open.pk].assigned_at)
            self.assertIn("Closed by migration 0010", rows[duplicate_open.pk].change_reason)
            self.assertIs(rows[newest_open.pk].is_current, True)

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectSupervisorAssignment.objects.create(project=reassigned, supervisor=first)


class ProjectStatusEventAppendOnlyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project, cls.supervisor, _ = _assignment_fixtures(" events")
        cls.event = ProjectStatusEvent.objects.create(
            project=cls.project,
            from_stage=ProjectStage.PROPOSED,
            to_stage=ProjectStage.SUPERVISOR_ACCEPTED,
            actor=cls.supervisor,
            note="Accepted",
        )

    def test_new_events_can_be_added(self):
        ProjectStatusEvent.objects.create(
            project=self.project, from_stage=ProjectStage.SUPERVISOR_ACCEPTED, to_stage=ProjectStage.APPROVED
        )

        self.assertEqual(self.project.status_events.count(), 2)

    def test_saved_event_cannot_be_changed(self):
        self.event.note = "Rewritten"

        with self.assertRaises(PermissionError):
            self.event.save()

        self.event.refresh_from_db()
        self.assertEqual(self.event.note, "Accepted")

    def test_event_cannot_be_deleted(self):
        with self.assertRaises(PermissionError):
            self.event.delete()

        self.assertTrue(ProjectStatusEvent.objects.filter(pk=self.event.pk).exists())

    def test_queryset_update_and_delete_are_refused(self):
        with self.assertRaises(PermissionError):
            ProjectStatusEvent.objects.filter(pk=self.event.pk).update(note="Rewritten")
        with self.assertRaises(PermissionError):
            self.project.status_events.all().delete()

        self.event.refresh_from_db()
        self.assertEqual(self.event.note, "Accepted")

    def test_admin_is_view_only(self):
        admin_user = User.objects.create_superuser(username="events.admin", password="test-password")
        self.client.force_login(admin_user)

        change = self.client.post(
            reverse("admin:projects_projectstatusevent_change", args=[self.event.pk]), {"note": "Rewritten"}
        )
        delete = self.client.post(
            reverse("admin:projects_projectstatusevent_delete", args=[self.event.pk]), {"post": "yes"}
        )

        self.assertEqual(change.status_code, 403)
        self.assertEqual(delete.status_code, 403)
        self.event.refresh_from_db()
        self.assertEqual(self.event.note, "Accepted")

    def test_deleting_a_project_or_user_still_cascades(self):
        # purge_demo deletes demo projects and users; the events go with the project,
        # and a deleted user's events keep their history with the actor cleared.
        other_project, other_actor, _ = _assignment_fixtures(" cascade")
        kept = ProjectStatusEvent.objects.create(
            project=self.project, to_stage=ProjectStage.APPROVED, actor=other_actor
        )
        ProjectStatusEvent.objects.create(project=other_project, to_stage=ProjectStage.PROPOSED)

        other_actor.delete()
        other_project.delete()

        kept.refresh_from_db()
        self.assertIsNone(kept.actor)
        self.assertFalse(ProjectStatusEvent.objects.filter(project_id=other_project.pk).exists())


class ApprovalDecisionHistoryTests(TestCase):
    """Every decision on the approval form is kept, even after the student revises and resubmits."""

    @classmethod
    def setUpTestData(cls):
        cls.project, cls.supervisor, cls.other = _assignment_fixtures(" decisions")
        # A coordinator who also supervises, so one person can decide and then log the form.
        cls.supervisor.role = Role.COORDINATOR
        cls.supervisor.first_name, cls.supervisor.last_name = "Ngozi", "Eze"
        cls.supervisor.save()
        cls.project.supervisor = cls.supervisor
        cls.project.save()

    def _submit(self, title):
        submit_proposal(
            self.project,
            proposed_title=title,
            problem_statement="Problem",
            objectives="Objectives",
            methodology="Method",
            tools_and_technologies="Django",
        )

    def _decide(self, decision, comments, user=None):
        record_supervisor_decision(
            Project.objects.get(pk=self.project.pk),
            supervisor=user or self.supervisor,
            decision=decision,
            comments=comments,
            name_on_form="N. Eze",
            signed_on=date(2026, 10, 1),
        )

    def test_rejection_survives_resubmission_and_full_history_is_kept(self):
        self._submit("First idea")
        self._decide(SupervisorDecision.REJECTED, "Narrow the scope")
        self.project.refresh_from_db()
        self._submit("Second idea")
        self._decide(SupervisorDecision.ACCEPTED, "Good")
        log_approved_form(
            Project.objects.get(pk=self.project.pk),
            coordinator=self.supervisor,
            notes="Filed in register",
            logged_on=date(2026, 10, 3),
        )

        form = ProjectApprovalForm.objects.get(project=self.project)
        self.assertEqual((form.proposed_title, form.supervisor_decision), ("Second idea", SupervisorDecision.ACCEPTED))
        history = list(self.project.approval_decisions.all())
        self.assertEqual(
            [(row.step, row.decision, row.proposed_title, row.comments) for row in history],
            [
                (ApprovalDecisionStep.SUPERVISOR, SupervisorDecision.REJECTED, "First idea", "Narrow the scope"),
                (ApprovalDecisionStep.SUPERVISOR, SupervisorDecision.ACCEPTED, "Second idea", "Good"),
                (ApprovalDecisionStep.COORDINATOR_LOG, "", "Second idea", "Filed in register"),
            ],
        )
        self.assertEqual([row.decided_by for row in history], [self.supervisor] * 3)
        self.assertEqual(history[0].decided_on, date(2026, 10, 1))
        self.assertEqual(history[2].decided_on, date(2026, 10, 3))
        self.assertEqual(history[2].name_on_form, "Ngozi Eze")
        self.assertEqual(history[0].approval_method, "topic_only")

    def test_refused_decision_leaves_no_record(self):
        self._submit("First idea")

        with self.assertRaises(ValidationError):
            self._decide(SupervisorDecision.ACCEPTED, "Not mine to decide", user=self.other)

        self.assertFalse(self.project.approval_decisions.exists())

    def test_decisions_cannot_be_changed_or_deleted(self):
        self._submit("First idea")
        self._decide(SupervisorDecision.REJECTED, "Narrow the scope")
        row = self.project.approval_decisions.get()

        row.comments = "Rewritten"
        with self.assertRaises(PermissionError):
            row.save()
        with self.assertRaises(PermissionError):
            row.delete()
        with self.assertRaises(PermissionError):
            ProjectApprovalDecision.objects.filter(pk=row.pk).update(comments="Rewritten")
        with self.assertRaises(PermissionError):
            self.project.approval_decisions.all().delete()

        row.refresh_from_db()
        self.assertEqual(row.comments, "Narrow the scope")


class CompletionGapCheckTests(TestCase):
    """HOD sign-off needs a documented gap, or an explicit confirmation that there is none."""

    @classmethod
    def setUpTestData(cls):
        cls.project, _, _ = _assignment_fixtures(" signoff")
        cls.project.stage = ProjectStage.DEFENDED
        cls.project.gap_summary = "Gap noted by the supervisor"
        cls.project.save()
        cls.hod = User.objects.create(username="signoff.hod", role=Role.HOD, department=cls.project.department)

    def _sign_off(self, **kwargs):
        return sign_off_completion(self.project, self.hod, signed_on=date(2026, 10, 5), **kwargs)

    def _assert_not_archived(self):
        self.project.refresh_from_db()
        self.assertFalse(self.project.archived)
        self.assertEqual(self.project.stage, ProjectStage.DEFENDED)
        self.assertFalse(ProjectCompletion.objects.filter(project=self.project).exists())

    def test_sign_off_without_gap_or_confirmation_is_refused(self):
        for blank in ("", "   "):
            with self.subTest(gap_summary=blank), self.assertRaises(ValidationError):
                self._sign_off(gap_summary=blank)
        self._assert_not_archived()

    def test_gap_and_no_gap_together_are_refused(self):
        with self.assertRaises(ValidationError):
            self._sign_off(gap_summary="Something", no_gap=True)
        self._assert_not_archived()

    def test_recorded_gap_is_carried_to_the_archive(self):
        completion, archived = self._sign_off(gap_summary="  Evaluate with more users  ")

        self.assertEqual(archived.gap_summary, "Evaluate with more users")
        self.assertFalse(completion.no_gap_confirmed)

    def test_no_gap_confirmation_archives_with_an_empty_gap(self):
        completion, archived = self._sign_off(no_gap=True)

        self.assertTrue(completion.no_gap_confirmed)
        self.assertEqual(archived.gap_summary, "")
        self.project.refresh_from_db()
        self.assertTrue(self.project.archived)

    def test_sign_off_page_prefills_gap_and_explains_a_refusal(self):
        self.client.force_login(self.hod)
        url = reverse("project_workflow", args=[self.project.pk])

        page = self.client.get(url)
        self.assertEqual(page.context["form"]["gap_summary"].value(), "Gap noted by the supervisor")

        response = self.client.post(url, {"signed_on": "2026-10-05", "gap_summary": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Record the documented gap, or confirm that there is none.", response.context["form"].non_field_errors())
        self._assert_not_archived()

        response = self.client.post(url, {"signed_on": "2026-10-05", "gap_summary": "", "no_gap": "on"})
        self.project.refresh_from_db()
        self.assertTrue(self.project.archived)
        # The past-project page itself stays hidden until graduation is verified, so don't follow it.
        self.assertRedirects(
            response,
            reverse("past_project_detail", args=[self.project.archive_record.pk]),
            fetch_redirect_response=False,
        )
