import tempfile
from datetime import datetime, timezone as dt_timezone

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent
from apps.supervision.models import Announcement

from .models import (
    ArchivedProject,
    Project,
    ProjectDocument,
    ProjectStage,
    ProjectSupervisorAssignment,
)
from .services import available_years


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
