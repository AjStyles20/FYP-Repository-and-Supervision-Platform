import tempfile
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from django.test import SimpleTestCase, TestCase, TransactionTestCase
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
    ProjectMilestone,
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
    record_transition,
    sign_off_completion,
    submit_proposal,
    unassign_project_supervisor,
)
from .services.similarity import similar_archived_projects, similarity, stem, tokens
from .services.health import AT_RISK, ON_TRACK, WATCH, health_band, health_score


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
            graduation_year=2026,
        )
        User.objects.filter(pk=cls.student.pk).update(personal_email="ada.contact@example.com", personal_email_visibility="signed_in")
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
        )
        User.objects.filter(pk=cls.alumni.pk).update(personal_email="grace.contact@example.com", personal_email_visibility="signed_in")
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

    @override_settings(PUBLIC_REPOSITORY=False)
    def test_repository_requires_authentication_when_the_public_showcase_is_off(self):
        response = self.client.get(reverse("repository"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('repository')}")

    def test_running_topics_always_require_authentication(self):
        response = self.client.get(reverse("running_topics"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('running_topics')}")

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

    def test_repository_lists_archived_work_before_graduation_is_verified(self):
        # Completion and graduation are separate facts: an archived project is listed whether or
        # not the student has graduated yet.
        unverified_project = ArchivedProject.objects.create(
            title="Awaiting verified graduation",
            year=2026,
            department=self.department,
            programme=self.programme,
            student=self.student,
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("repository"))

        self.assertContains(response, unverified_project.title)
        self.assertIn(2026, response.context["years"])

    def test_completed_project_detail_shows_graduation_separately(self):
        self.client.force_login(self.alumni)
        self.profile.student_status = StudentProfile.Status.FYP_COMPLETED
        self.profile.save(update_fields=["student_status"])
        unverified_project = ArchivedProject.objects.create(
            title="Completed, not yet graduated",
            year=2026,
            department=self.department,
            programme=self.programme,
            student=self.student,
        )

        response = self.client.get(reverse("past_project_detail", args=[unverified_project.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not yet verified (project completed)")
        # graduation_year is set on this profile, but status is not GRADUATED, so it is not shown
        # as a verified graduation.
        self.assertNotContains(response, "Verified graduation year")

    def test_signed_off_project_without_graduation_appears_in_repository(self):
        project = Project.objects.create(
            student=self.student, title="Signed off before graduation", department=self.department,
            programme=self.programme, supervisor=self.supervisor, stage=ProjectStage.DEFENDED,
        )
        ProjectDocument.objects.create(
            project=project, title="Final report", document_type="report",
            file=SimpleUploadedFile("final.pdf", b"%PDF-1.4 report"),
        )
        _, archived = sign_off_completion(
            project, self.hod, signed_on=date(2026, 10, 5), gap_summary="Scale the pilot", graduation_verified=False,
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.student_status, StudentProfile.Status.FYP_COMPLETED)

        self.client.force_login(self.alumni)
        listing = self.client.get(reverse("repository"))
        detail = self.client.get(reverse("past_project_detail", args=[archived.pk]))
        document = archived.documents.get()
        download = self.client.get(reverse("download_project_document", args=[document.pk]))

        self.assertContains(listing, "Signed off before graduation")
        self.assertContains(detail, "Scale the pilot")
        self.assertEqual(download.status_code, 200)
        # Read the stream rather than calling close(): close() fires request_finished, which
        # closes the database connection and breaks the test transaction on MySQL.
        self.assertEqual(b"".join(download.streaming_content), b"%PDF-1.4 report")

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
        self.assertNotContains(response, "student identification number")

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

    def test_current_project_files_are_limited_to_the_project_department(self):
        document = ProjectDocument.objects.create(
            project=self.current_project,
            title="Draft report",
            document_type="report",
            file=SimpleUploadedFile("draft.pdf", b"draft report"),
            visibility=ProjectDocument.Visibility.STAFF_ONLY,
            uploaded_by=self.student,
        )
        # Another faculty: a coordinator sees every department of their own faculty (D-43).
        other_department = Department.objects.create(faculty=Faculty.objects.create(name="Other Faculty"), name="Software Engineering")
        allowed = {
            "own student": self.student,
            "assigned supervisor": self.supervisor,
            "department coordinator": self.coordinator,
            "department Head of Department": self.hod,
            "administrator": self.admin,
        }
        refused = {
            "another student": self.alumni,
            "supervisor of another department": User.objects.create(
                username="doc.other.supervisor", role=Role.SUPERVISOR, department=other_department
            ),
            "coordinator of another department": User.objects.create(
                username="doc.other.coordinator", role=Role.COORDINATOR, department=other_department
            ),
            "Head of Department with no department": User.objects.create(username="doc.nodept.hod", role=Role.HOD),
        }
        url = reverse("download_project_document", args=[document.pk])

        for label, user in allowed.items():
            with self.subTest(user=label):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(b"".join(response.streaming_content), b"draft report")
        for label, user in refused.items():
            with self.subTest(user=label):
                self.client.force_login(user)
                self.assertEqual(self.client.get(url).status_code, 404)

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


def _assignment_fixtures(suffix="", project_model=Project):
    """A department, two supervisors and a student project, for the assignment constraint tests.

    A migration test passes the historical Project model, whose table has fewer columns.
    """
    faculty = Faculty.objects.create(name=f"Assignment Faculty{suffix}")
    department = Department.objects.create(faculty=faculty, name=f"Assignment Department{suffix}")
    programme = Programme.objects.create(department=department, name="Software Engineering", degree_type="BSc")
    student = User.objects.create(username=f"assign.student{suffix}", role=Role.STUDENT)
    first = User.objects.create(username=f"assign.first{suffix}", role=Role.SUPERVISOR, department=department)
    second = User.objects.create(username=f"assign.second{suffix}", role=Role.SUPERVISOR, department=department)
    project = project_model.objects.create(
        student_id=student.pk, title=f"Assignment project{suffix}", department_id=department.pk, programme_id=programme.pk
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
        # TransactionTestCase empties every table afterwards; the audit triggers would refuse
        # that on SQLite if this test had written any audit events.
        self.assertFalse(AuditEvent.objects.exists())

    def test_existing_rows_are_converted_and_the_constraint_added(self):
        old_apps = self.executor.loader.project_state(self.before).apps
        OldAssignment = old_apps.get_model("projects", "ProjectSupervisorAssignment")
        # The projects are made with the old model too: today's Project has columns (such as its
        # semester) that the schema at 0009 does not have yet.
        reassigned, first, second = _assignment_fixtures(" A", project_model=old_apps.get_model("projects", "Project"))
        unassigned, third, _ = _assignment_fixtures(" B", project_model=old_apps.get_model("projects", "Project"))
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
        reassigned, unassigned = Project.objects.get(pk=reassigned.pk), Project.objects.get(pk=unassigned.pk)

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
    """Head of Department sign-off needs a documented gap, or an explicit confirmation that there is none."""

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


class CoordinatorDepartmentStepTests(TestCase):
    """Logging approval and recording the defence belong to any coordinator of the faculty (D-43)."""

    @classmethod
    def setUpTestData(cls):
        cls.project, cls.supervisor, _ = _assignment_fixtures(" coordinator")
        cls.project.supervisor = cls.supervisor
        cls.project.save()
        cls.coordinator = User.objects.create(
            username="dept.coordinator", role=Role.COORDINATOR, department=cls.project.department
        )
        other_project, _, _ = _assignment_fixtures(" elsewhere")  # another faculty
        cls.outside_coordinator = User.objects.create(
            username="outside.coordinator", role=Role.COORDINATOR, department=other_project.department
        )
        # A coordinator whose own department (their teaching field) is a sister department of the same faculty.
        sister = Department.objects.create(faculty=cls.project.department.faculty, name="Sister Department")
        cls.faculty_coordinator = User.objects.create(username="faculty.coordinator", role=Role.COORDINATOR, department=sister)

    def _accepted_by_supervisor(self):
        submit_proposal(
            self.project, proposed_title="Idea", problem_statement="P", objectives="O",
            methodology="M", tools_and_technologies="Django",
        )
        record_supervisor_decision(
            Project.objects.get(pk=self.project.pk), supervisor=self.supervisor,
            decision=SupervisorDecision.ACCEPTED, comments="", name_on_form="S", signed_on=date(2026, 10, 1),
        )

    def _set_stage(self, stage):
        Project.objects.filter(pk=self.project.pk).update(stage=stage)

    def _stage(self):
        return Project.objects.get(pk=self.project.pk).stage

    def test_department_coordinator_logs_approval_on_a_project_they_do_not_supervise(self):
        self._accepted_by_supervisor()

        log_approved_form(
            Project.objects.get(pk=self.project.pk), coordinator=self.coordinator,
            notes="Filed", logged_on=date(2026, 10, 2),
        )

        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual((project.stage, project.approval_date), (ProjectStage.APPROVED, date(2026, 10, 2)))
        self.assertEqual(project.status_events.first().actor, self.coordinator)

    def test_department_coordinator_records_defence_on_a_project_they_do_not_supervise(self):
        self._set_stage(ProjectStage.SUBMITTED)

        record_transition(self.project, ProjectStage.DEFENDED, actor=self.coordinator, when=date(2026, 10, 4))

        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual((project.stage, project.defence_date), (ProjectStage.DEFENDED, date(2026, 10, 4)))

    def test_department_coordinator_can_do_both_through_the_workflow_page(self):
        self._accepted_by_supervisor()
        self.client.force_login(self.coordinator)
        url = reverse("project_workflow", args=[self.project.pk])

        self.client.post(url, {"notes": "Filed", "logged_on": "2026-10-02"})
        self.assertEqual(self._stage(), ProjectStage.APPROVED)

        self._set_stage(ProjectStage.SUBMITTED)
        self.client.post(url, {"note": "Passed", "when": "2026-10-04"})
        self.assertEqual(self._stage(), ProjectStage.DEFENDED)

    def test_a_coordinator_from_a_sister_department_of_the_faculty_does_both_through_the_workflow_page(self):
        self._accepted_by_supervisor()
        self.client.force_login(self.faculty_coordinator)
        url = reverse("project_workflow", args=[self.project.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertIn(self.project, self.client.get(reverse("approvals")).context["projects"])

        self.client.post(url, {"notes": "Filed", "logged_on": "2026-10-02"})
        self.assertEqual(self._stage(), ProjectStage.APPROVED)

        self._set_stage(ProjectStage.SUBMITTED)
        self.client.post(url, {"note": "Passed", "when": "2026-10-04"})
        self.assertEqual(self._stage(), ProjectStage.DEFENDED)

    def test_coordinator_from_another_faculty_cannot_open_the_project(self):
        self.client.force_login(self.outside_coordinator)
        self.assertEqual(self.client.get(reverse("project_workflow", args=[self.project.pk])).status_code, 403)
        self.assertNotIn(self.project, self.client.get(reverse("approvals")).context["projects"])

    def test_coordinator_from_another_department_cannot_log_approval_or_record_defence(self):
        self._accepted_by_supervisor()

        with self.assertRaises(ValidationError):
            log_approved_form(
                Project.objects.get(pk=self.project.pk), coordinator=self.outside_coordinator,
                notes="", logged_on=date(2026, 10, 2),
            )
        self.assertEqual(self._stage(), ProjectStage.SUPERVISOR_ACCEPTED)

        self._set_stage(ProjectStage.SUBMITTED)
        with self.assertRaises(ValidationError):
            record_transition(self.project, ProjectStage.DEFENDED, actor=self.outside_coordinator)
        self.assertEqual(self._stage(), ProjectStage.SUBMITTED)

        self.client.force_login(self.outside_coordinator)
        response = self.client.post(
            reverse("project_workflow", args=[self.project.pk]), {"note": "Passed", "when": "2026-10-04"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._stage(), ProjectStage.SUBMITTED)

    def test_supervisor_steps_still_need_the_assigned_supervisor(self):
        self._set_stage(ProjectStage.APPROVED)

        with self.assertRaises(ValidationError):
            record_transition(self.project, ProjectStage.IN_PROGRESS, actor=self.coordinator)
        self.assertEqual(self._stage(), ProjectStage.APPROVED)


class UnassignedProjectPagesTests(TestCase):
    """A proposal with no supervisor yet must not break the pages that list it."""

    @classmethod
    def setUpTestData(cls):
        cls.project, _, _ = _assignment_fixtures(" unassigned")
        cls.coordinator = User.objects.create(
            username="unassigned.coordinator", role=Role.COORDINATOR, department=cls.project.department
        )

    def test_approval_register_lists_a_proposal_without_a_supervisor(self):
        self.client.force_login(self.coordinator)

        response = self.client.get(reverse("approvals"))

        self.assertContains(response, "Assignment project unassigned")
        self.assertContains(response, "Supervisor: Not assigned")

    def test_student_my_project_page_before_a_supervisor_is_assigned(self):
        self.client.force_login(self.project.student)

        response = self.client.get(reverse("my_project"))

        self.assertContains(response, "Supervisor to be assigned")


class SimilarityScoreTests(SimpleTestCase):
    """similarity(a, b) is the Jaccard index of the two word sets after cleaning."""

    def test_identical_text_scores_one(self):
        self.assertEqual(similarity("Exam Seating Allocation Tool", "Exam Seating Allocation Tool"), 1.0)

    def test_case_punctuation_and_stop_words_are_ignored(self):
        self.assertEqual(tokens("The Exam-Seating tool, for halls!"), {"exam", "seat", "tool", "hall"})
        self.assertEqual(similarity("The Exam-Seating Tool!", "exam seating tool"), 1.0)

    def test_plural_and_ing_endings_are_stripped(self):
        self.assertEqual({stem(word) for word in ("seat", "seats", "seating")}, {"seat"})
        self.assertEqual([stem(word) for word in ("studies", "delays", "booking", "running")],
                         ["study", "delay", "book", "run"])
        # Left alone: ss/us/is endings, and -ing words that would lose their only vowel or get too short.
        self.assertEqual([stem(word) for word in ("class", "bus", "analysis", "string", "thing")],
                         ["class", "bus", "analysis", "string", "thing"])

    def test_suffix_stripping_lifts_the_seat_example_over_the_threshold(self):
        score = similarity(
            "Exam Seat Allocation for Lecture Halls",
            "Exam Seating Allocation Tool A decision-support tool for allocating examination seats across halls.",
        )
        self.assertAlmostEqual(score, 4 / 11)  # {allocation, exam, hall, seat} of 11 words; was 3/13 without
        self.assertGreaterEqual(score, 0.35)

    def test_partly_overlapping_text_scores_shared_over_all_words(self):
        # {campus, shuttle, delay, tracker} versus {campus, shuttle, booking, app}: 2 shared of 6 words.
        self.assertAlmostEqual(similarity("Campus Shuttle Delay Tracker", "A campus shuttle booking app"), 2 / 6)

    def test_unrelated_text_scores_zero(self):
        self.assertEqual(similarity("Cafeteria Queue Predictor", "Exam Seating Allocation Tool"), 0.0)

    def test_empty_text_scores_zero(self):
        self.assertEqual(similarity("", ""), 0.0)
        self.assertEqual(similarity("", "Exam Seating Allocation Tool"), 0.0)
        self.assertEqual(similarity(None, None), 0.0)
        self.assertEqual(similarity("the and of", "the and of"), 0.0)  # only stop-words left nothing


class SimilarTopicPagesTests(TestCase):
    """The checker warns on topic submission and lists matches on the repository detail page."""

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Similarity Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Similarity Department")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.student = User.objects.create(username="similar.student", role=Role.STUDENT)
        StudentProfile.objects.create(
            user=cls.student, student_number="BU/26/CS/9001", programme=cls.programme,
            registration_status=StudentProfile.RegistrationStatus.APPROVED,
        )
        cls.alumni = User.objects.create(username="similar.alumni", role=Role.STUDENT)
        cls.seating = cls._archive("Exam Seating Allocation Tool", "Allocating examination seats across halls.", 2024)
        cls.cafeteria = cls._archive("Cafeteria Queue Predictor", "Predicts queue length from sales.", 2025)

    @classmethod
    def _archive(cls, title, description, year):
        return ArchivedProject.objects.create(
            title=title, description=description, year=year, department=cls.department,
            programme=cls.programme, student=cls.alumni,
        )

    def test_similar_topic_warns_but_the_project_is_still_created(self):
        self.client.force_login(self.student)

        response = self.client.post(reverse("start_project"), {
            "title": "Exam Seating Allocation Tool", "description": "Allocating examination seats across lecture halls.",
        }, follow=True)

        project = Project.objects.get(student=self.student)
        self.assertRedirects(response, reverse("project_workflow", args=[project.pk]))
        self.assertContains(response, "1 archived project looks similar")
        self.assertContains(response, reverse("past_project_detail", args=[self.seating.pk]))
        self.assertNotContains(response, "Cafeteria Queue Predictor")

    def test_unrelated_topic_gives_no_warning(self):
        self.client.force_login(self.student)

        response = self.client.post(reverse("start_project"), {"title": "Hostel Laundry Booking"}, follow=True)

        self.assertTrue(Project.objects.filter(student=self.student).exists())
        self.assertNotContains(response, "looks similar")
        self.assertContains(response, "No archived project scores 0.35 or higher.")

    def test_proposal_with_a_similar_title_is_saved_with_a_warning(self):
        project = Project.objects.create(
            student=self.student, title="Working title", department=self.department, programme=self.programme,
        )
        self.client.force_login(self.student)

        response = self.client.post(reverse("project_workflow", args=[project.pk]), {
            "proposed_title": "Exam Seating Allocation Tool for Halls",
            "problem_statement": "Seats are allocated by hand.", "objectives": "Automate it.", "methodology": "Prototype.",
        }, follow=True)

        self.assertTrue(ProjectApprovalForm.objects.filter(project=project).exists())
        self.assertContains(response, "Your topic was saved")
        self.assertContains(response, "Exam Seating Allocation Tool</a>")

    def test_detail_page_shows_the_top_five_best_first_and_not_itself(self):
        for number in range(6):
            self._archive(f"Exam Seating Allocation Tool {number}", "Allocating examination seats across halls.", 2020 + number)
        self.client.force_login(self.student)

        response = self.client.get(reverse("past_project_detail", args=[self.seating.pk]))

        matches = response.context["similar_projects"]
        self.assertEqual(len(matches), 5)
        self.assertNotIn(self.seating.pk, [match["id"] for match in matches])
        self.assertEqual([match["score"] for match in matches], sorted((match["score"] for match in matches), reverse=True))
        self.assertContains(response, "Similar past projects")

    def test_current_project_detail_lists_similar_archived_projects(self):
        project = Project.objects.create(
            student=self.student, title="Exam Seating Allocation Tool", description="Allocating examination seats across halls.",
            department=self.department, programme=self.programme,
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("current_project_detail", args=[project.pk]))

        self.assertEqual([match["id"] for match in response.context["similar_projects"]], [self.seating.pk])
        self.assertContains(response, "1.00")

    @override_settings(SIMILARITY_THRESHOLD=0.99)
    def test_threshold_comes_from_settings(self):
        self.assertEqual(similar_archived_projects("Exam Seating Allocation Tool for Halls"), [])
        self.assertEqual(len(similar_archived_projects("Exam Seating Allocation Tool", "Allocating examination seats across halls.")), 1)


class ProjectHealthScoreTests(TestCase):
    """health_score(project, now): edge cases with records created now and `now` moved forward."""

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Health Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Health Department")
        # Another faculty: a coordinator sees their whole faculty (D-29), so the outsider must be outside it.
        cls.other_department = Department.objects.create(
            faculty=Faculty.objects.create(name="Other Health Faculty"), name="Other Health Department"
        )
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.supervisor = User.objects.create(username="health.supervisor", role=Role.SUPERVISOR, department=cls.department)
        cls.coordinator = User.objects.create(username="health.coordinator", role=Role.COORDINATOR, department=cls.department)
        cls.other_coordinator = User.objects.create(
            username="health.other.coordinator", role=Role.COORDINATOR, department=cls.other_department
        )
        cls.hod = User.objects.create(username="health.hod", role=Role.HOD, department=cls.department)
        cls.student = User.objects.create(username="health.student", role=Role.STUDENT)

    def _project(self, stage=ProjectStage.IN_PROGRESS, supervised=True):
        project = Project.objects.create(
            student=self.student, title="Health project", department=self.department, programme=self.programme,
            stage=stage, supervisor=self.supervisor if supervised else None,
        )
        ProjectStatusEvent.objects.create(project=project, to_stage=stage, note="Created for the health tests.")
        if supervised:
            ProjectSupervisorAssignment.objects.create(project=project, supervisor=self.supervisor)
        return project

    def _meeting(self, project, when, status):
        from apps.supervision.models import SupervisionMeeting

        return SupervisionMeeting.objects.create(project=project, scheduled_for=when, status=status)

    def _later(self, days):
        return timezone.now() + timedelta(days=days)

    def test_brand_new_project_is_on_track_with_every_reason_listed(self):
        project = self._project(stage=ProjectStage.PROPOSED, supervised=False)

        health = health_score(project)

        self.assertEqual(health.score, 0)
        self.assertEqual(health.band, ON_TRACK)
        self.assertEqual(health.reasons, [
            "No held meeting yet; project created 0 days ago (limit 14 days): +0",
            "No milestones set: +0",
            "0 days at Topic proposed (expected 14 days): +0",
        ])

    def test_no_meetings_counts_from_the_supervisor_assignment(self):
        project = self._project()

        health = health_score(project, now=self._later(20))

        # meeting 0.4 * min(20/14, 1) = 0.4; stage 0.3 * 20/90 = 0.0667; no milestones.
        self.assertEqual(health.score, 47)
        self.assertEqual(health.band, WATCH)
        self.assertIn("No held meeting yet; supervisor assigned 20 days ago (limit 14 days): +40", health.reasons)
        self.assertIn("No milestones set: +0", health.reasons)

    def test_only_held_meetings_reset_the_clock(self):
        project = self._project()
        now = self._later(30)
        self._meeting(project, now - timedelta(days=7), "held")
        self._meeting(project, now - timedelta(days=1), "missed")
        self._meeting(project, now - timedelta(days=2), "scheduled")

        health = health_score(project, now=now)

        self.assertIn("Last held meeting 7 days ago (limit 14 days): +20", health.reasons)

    def test_every_term_is_capped_and_the_total_is_at_risk(self):
        project = self._project()
        now = self._later(120)
        self._meeting(project, now - timedelta(days=60), "held")
        for number in range(4):
            ProjectMilestone.objects.create(project=project, name=f"Chapter {number}", due_date=date(2020, 1, 1))

        health = health_score(project, now=now)

        self.assertEqual(health.score, 100)
        self.assertEqual(health.band, AT_RISK)
        self.assertIn("4 overdue milestones (limit 3): +30", health.reasons)
        self.assertIn("120 days at In progress (expected 90 days): +30", health.reasons)

    def test_done_undated_and_future_milestones_are_not_overdue(self):
        project = self._project()
        ProjectMilestone.objects.create(project=project, name="Done", due_date=date(2020, 1, 1), done=True)
        ProjectMilestone.objects.create(project=project, name="Undated")
        ProjectMilestone.objects.create(project=project, name="Future", due_date=timezone.localdate() + timedelta(days=30))

        health = health_score(project)

        self.assertIn("0 overdue milestones (limit 3): +0", health.reasons)

    def test_completed_and_archived_projects_have_no_score(self):
        self.assertIsNone(health_score(self._project(stage=ProjectStage.COMPLETED)))
        archived = self._project()
        archived.archived = True
        self.assertIsNone(health_score(archived))

    def test_band_edges(self):
        self.assertEqual([health_band(score) for score in (0, 29, 30, 60, 61, 100)],
                         [ON_TRACK, ON_TRACK, WATCH, WATCH, AT_RISK, AT_RISK])

    @override_settings(HEALTH_WEIGHTS={"meeting": 1.0, "milestones": 0.0, "stage": 0.0}, HEALTH_BANDS={"watch": 10, "at_risk": 20})
    def test_weights_and_bands_come_from_settings(self):
        health = health_score(self._project(), now=self._later(7))

        self.assertEqual(health.score, 50)
        self.assertEqual(health.band, AT_RISK)

    def test_supervisor_and_department_coordinator_see_health_on_the_workflow_page(self):
        project = self._project()
        for viewer in (self.supervisor, self.coordinator):
            self.client.force_login(viewer)
            response = self.client.get(reverse("project_workflow", args=[project.pk]))
            self.assertContains(response, "Project health (heuristic)", msg_prefix=viewer.username)
            self.assertContains(response, "No milestones set: +0", msg_prefix=viewer.username)

    def test_hod_and_student_do_not_see_health(self):
        project = self._project()
        for viewer in (self.hod, self.student):
            self.client.force_login(viewer)
            response = self.client.get(reverse("project_workflow", args=[project.pk]))
            self.assertEqual(response.status_code, 200, viewer.username)
            self.assertNotContains(response, "Project health", msg_prefix=viewer.username)

    def test_supervision_page_and_coordinator_portal_list_health(self):
        self._project()
        self.client.force_login(self.supervisor)
        self.assertContains(self.client.get(reverse("supervision")), "On track · 0/100")

        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Projects by health score")
        self.assertContains(response, "On track · 0/100")

        self.client.force_login(self.other_coordinator)
        self.assertNotContains(self.client.get(reverse("dashboard")), "On track · 0/100")


class ProjectStartKeywordsTests(TestCase):
    """Keywords are optional, and the start form says what they are for."""

    def test_keywords_are_optional_and_explained(self):
        faculty = Faculty.objects.create(name="Keyword Faculty")
        department = Department.objects.create(faculty=faculty, name="Computer Science")
        programme = Programme.objects.create(department=department, name="Computer Science", degree_type="BSc")
        student = User.objects.create(username="kw.student", role=Role.STUDENT)
        StudentProfile.objects.create(user=student, student_number="BU/23A/CS/7001", programme=programme)
        self.client.force_login(student)

        page = self.client.get(reverse("start_project"))
        self.assertContains(page, "Keywords (optional)")
        self.assertContains(page, "They help people find the project in a search.")
        self.assertContains(page, 'placeholder="For example fintech, fraud detection, mobile money"')

        self.client.post(reverse("start_project"), {"title": "Library Seat Booking", "description": "", "keywords": ""})
        self.assertEqual(Project.objects.get(student=student).keywords, "")


class SupervisorProvidedDocumentTests(TestCase):
    """The report instructions on the Project guide: every signed-in user, never the public."""

    def test_everyone_signed_in_sees_and_downloads_them_and_visitors_do_not(self):
        for role in (Role.STUDENT, Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN):
            with self.subTest(role=role):
                self.client.force_login(User.objects.create(username=f"guide.{role}", role=role))
                page = self.client.get(reverse("guidelines"))
                self.assertContains(page, "Supervisor-provided documents")
                for name in ("final-year-project-report-instructions.pdf", "final-year-project-report-instructions.docx"):
                    self.assertContains(page, reverse("department_document", args=[name]))
                download = self.client.get(reverse("department_document", args=["final-year-project-report-instructions.pdf"]))
                self.assertEqual(download.status_code, 200)
                self.assertIn('attachment; filename="final-year-project-report-instructions.pdf"', download["Content-Disposition"])
                self.assertTrue(b"".join(download.streaming_content).startswith(b"%PDF"))
        self.client.logout()
        response = self.client.get(reverse("department_document", args=["final-year-project-report-instructions.pdf"]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_only_the_listed_documents_can_be_downloaded(self):
        self.client.force_login(User.objects.create(username="guide.reader", role=Role.STUDENT))
        for name in ("settings.py", "..", "final-year-project-report-instructions.txt"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse("department_document", args=[name])).status_code, 404)
