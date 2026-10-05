import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User

from .models import (
    ArchivedProject,
    Project,
    ProjectDocument,
    ProjectStage,
    ProjectSupervisorAssignment,
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
            student=cls.student,
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

    def test_supervision_and_approval_pages_render_project_links(self):
        self.client.force_login(self.coordinator)
        self.assertEqual(self.client.get(reverse("supervision")).status_code, 200)

        self.current_project.stage = ProjectStage.PROPOSED
        self.current_project.save(update_fields=["stage"])
        response = self.client.get(reverse("approvals"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("current_project_detail", args=[self.current_project.pk]))

    def test_repository_has_current_and_past_sections(self):
        self.client.force_login(self.student)

        current_response = self.client.get(reverse("repository"), {"section": "current"})
        past_response = self.client.get(reverse("repository"), {"section": "past"})

        self.assertContains(current_response, "Campus Transport Analytics")
        self.assertContains(current_response, "Sample data")
        self.assertNotContains(current_response, "Student Support Portal")
        self.assertContains(past_response, "Student Support Portal")
        self.assertNotContains(past_response, "Campus Transport Analytics")
        self.assertContains(current_response, "Past students")
        self.assertContains(past_response, "Current students")

    def test_repository_searches_topics_students_and_supervisors(self):
        self.client.force_login(self.student)

        for search_term in ("Transport Analytics", "Ada", "Okoro"):
            with self.subTest(search_term=search_term):
                response = self.client.get(reverse("repository"), {"section": "current", "q": search_term})
                self.assertContains(response, "Campus Transport Analytics")

    def test_student_id_search_is_not_available_to_students(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("repository"), {"section": "current", "q": "BU/26/CS/1234"})

        self.assertNotContains(response, "Campus Transport Analytics")
        self.assertNotContains(response, "student ID")

    def test_staff_can_search_by_student_id(self):
        staff = User.objects.create_user(
            username="review.coordinator",
            password="test-password",
            role=Role.COORDINATOR,
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("repository"), {"section": "current", "q": "BU/26/CS/1234"})

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
        self.assertContains(response, "2026")
        self.assertContains(response, "Archive year 2025")
        self.assertContains(response, "Earlier supervisor")
        self.assertContains(response, "B Earlier")

    def test_filters_apply_to_both_repository_sections(self):
        self.client.force_login(self.student)

        response = self.client.get(
            reverse("repository"),
            {"section": "all", "department": self.department.pk},
        )

        self.assertContains(response, "Campus Transport Analytics")
        self.assertContains(response, "Student Support Portal")

    def test_archived_projects_are_not_listed_as_current(self):
        self.current_project.archived = True
        self.current_project.save(update_fields=["archived"])
        self.client.force_login(self.student)

        response = self.client.get(reverse("repository"), {"section": "current"})

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
