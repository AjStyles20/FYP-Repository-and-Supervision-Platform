from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, SupervisorProfile, User
from apps.projects.models import ArchivedProject, Project, ProjectSupervisorAssignment
from apps.supervision.models import Announcement, SharedResource, SupervisionMeeting


def run(*args, **kwargs):
    """Django's test runner always sets DEBUG=False, so seeding in tests needs --force."""
    if args and args[0] == "seed_demo":
        kwargs.setdefault("force", True)
    call_command(*args, stdout=StringIO(), stderr=StringIO(), **kwargs)


class LoginAndRolesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        run("seed_demo", password="pass-for-tests-1")

    def login(self, username):
        self.assertTrue(self.client.login(username=username, password="pass-for-tests-1"))

    def test_anonymous_is_sent_to_login(self):
        for url in (reverse("dashboard"), reverse("academic_structure"), reverse("admin_tools")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response["Location"])

    def test_each_role_sees_its_own_dashboard(self):
        expected = {
            "demo.amina": "Your project",
            "demo.okoro": "Your students",
            "demo.coordinator": "Coordinator",
            "demo.hod": "Head of Department",
            "demo.admin": "Administrator",
        }
        for username, heading in expected.items():
            self.client.logout()
            self.login(username)
            response = self.client.get(reverse("dashboard"))
            self.assertEqual(response.status_code, 200, username)
            self.assertContains(response, heading)

    def test_role_dashboards_use_separate_portal_templates(self):
        expected = {
            "demo.amina": "portals/student_current.html",
            "demo.okoro": "portals/supervisor.html",
            "demo.coordinator": "portals/coordinator.html",
            "demo.hod": "portals/hod.html",
            "demo.admin": "portals/admin.html",
        }
        for username, template in expected.items():
            with self.subTest(username=username):
                self.client.logout()
                self.login(username)
                response = self.client.get(reverse("dashboard"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)

    def test_graduated_students_have_a_separate_alumni_portal(self):
        student = User.objects.get(username="demo.amina")
        self.client.force_login(student)
        current_response = self.client.get(reverse("student_portal"))
        self.assertTemplateUsed(current_response, "portals/student_current.html")

        student.student_profile.student_status = StudentProfile.Status.GRADUATED
        student.student_profile.graduation_year = 2026
        student.student_profile.save(update_fields=["student_status", "graduation_year"])

        alumni_response = self.client.get(reverse("dashboard"))
        self.assertTemplateUsed(alumni_response, "portals/student_alumni.html")
        self.assertContains(alumni_response, "Past student / alumni portal")
        self.assertContains(alumni_response, "2026")
        self.assertRedirects(self.client.get(reverse("student_portal")), reverse("alumni_portal"))

    def test_student_portal_shows_supervisor_updates_and_unread_notifications(self):
        student = User.objects.get(username="demo.amina")
        project = Project.objects.get(student=student, archived=False)
        supervisor = project.supervisor
        Announcement.objects.create(
            author=supervisor,
            project=project,
            title="Updated literature review guide",
            body="Please use the new citation format for chapter two.",
        )
        SupervisionMeeting.objects.create(
            project=project,
            scheduled_for=timezone.now(),
            status="held",
            discussion="Reviewed the literature and identified missing sources.",
            corrective_action="Add citations to chapter two before the next meeting.",
            recorded_by=supervisor,
        )
        SharedResource.objects.create(
            author=supervisor,
            project=project,
            title="Department citation guide",
            url="https://example.com/citation-guide",
        )
        self.client.force_login(student)

        response = self.client.get(reverse("student_portal"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 new update")
        self.assertContains(response, "Updated literature review guide")
        self.assertContains(response, "Add citations to chapter two")
        self.assertContains(response, "Department citation guide")
        self.assertContains(response, reverse("running_topics"))
        self.assertContains(response, reverse("repository"))

    def test_student_cannot_open_staff_or_admin_pages(self):
        self.login("demo.amina")
        self.assertEqual(self.client.get(reverse("academic_structure")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin_tools")).status_code, 403)

    def test_staff_roles_can_open_academic_structure(self):
        for username in ("demo.okoro", "demo.coordinator", "demo.hod", "demo.admin"):
            self.client.logout()
            self.login(username)
            self.assertEqual(self.client.get(reverse("academic_structure")).status_code, 200, username)

    def test_only_admin_can_open_admin_tools(self):
        for username in ("demo.okoro", "demo.coordinator", "demo.hod"):
            self.client.logout()
            self.login(username)
            self.assertEqual(self.client.get(reverse("admin_tools")).status_code, 403, username)
        self.client.logout()
        self.login("demo.admin")
        self.assertEqual(self.client.get(reverse("admin_tools")).status_code, 200)

    def test_wrong_password_is_rejected(self):
        response = self.client.post(reverse("login"), {"username": "demo.amina", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "incorrect")

    def test_logout_requires_post(self):
        self.login("demo.amina")
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 302)


class SeedAndPurgeTests(TestCase):
    def test_seed_creates_expected_demo_data(self):
        run("seed_demo")
        self.assertEqual(User.objects.filter(is_demo=True, role=Role.STUDENT).count(), 6)
        self.assertEqual(User.objects.filter(is_demo=True, role=Role.SUPERVISOR).count(), 3)
        self.assertEqual(SupervisorProfile.objects.count(), 3)
        self.assertEqual(StudentProfile.objects.count(), 6)
        self.assertEqual(Faculty.objects.filter(is_demo=True).count(), 2)
        self.assertEqual(User.objects.get(username="demo.amina").email, "amina@bazeuniversity.edu.ng")
        self.assertEqual(Project.objects.filter(is_demo=True).count(), 4)
        self.assertEqual(ProjectSupervisorAssignment.objects.filter(ended_at__isnull=True).count(), 4)
        self.assertEqual(ArchivedProject.objects.filter(is_demo=True).count(), 2)

    def test_seed_is_repeatable(self):
        run("seed_demo")
        before = User.objects.count()
        run("seed_demo")
        self.assertEqual(User.objects.count(), before)
        self.assertEqual(ProjectSupervisorAssignment.objects.filter(ended_at__isnull=True).count(), 4)

    @override_settings(DEBUG=False)
    def test_seed_refuses_without_force_when_not_debug(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", force=False, stdout=StringIO(), stderr=StringIO())
        run("seed_demo")
        self.assertTrue(User.objects.filter(is_demo=True).exists())

    def test_purge_removes_only_demo_rows(self):
        run("seed_demo")
        real_faculty = Faculty.objects.create(name="Real Faculty")
        real_dept = Department.objects.create(faculty=real_faculty, name="Real Dept")
        real_user = User.objects.create_user("real.user", password="x-real-pass-1", role=Role.SUPERVISOR, department=real_dept)
        run("purge_demo")
        self.assertFalse(User.objects.filter(is_demo=True).exists())
        self.assertFalse(Faculty.objects.filter(is_demo=True).exists())
        self.assertFalse(Programme.objects.filter(is_demo=True).exists())
        self.assertFalse(Project.objects.filter(is_demo=True).exists())
        self.assertFalse(ArchivedProject.objects.filter(is_demo=True).exists())
        self.assertTrue(User.objects.filter(pk=real_user.pk).exists())
        self.assertTrue(Faculty.objects.filter(pk=real_faculty.pk).exists())

    def test_student_number_is_unique(self):
        from django.db import IntegrityError, transaction

        run("seed_demo")
        existing = StudentProfile.objects.first()
        other = User.objects.create_user("dup.student", password="x-real-pass-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentProfile.objects.create(user=other, student_number=existing.student_number, programme=existing.programme)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RegistrationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Registration Test Faculty")
        department = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.programme = Programme.objects.create(
            department=department,
            name="Computer Science",
            degree_type="BSc",
        )
        cls.password = "Secur3!LongPassword-2026"

    def registration_data(self, **overrides):
        data = {
            "first_name": "Ada",
            "last_name": "Student",
            "email": "ada.student@bazeuniversity.edu.ng",
            "student_number": "BU/26/CS/1001",
            "programme": self.programme.pk,
            "student_status": StudentProfile.Status.CURRENT,
            "password1": self.password,
            "password2": self.password,
        }
        data.update(overrides)
        return data

    def test_student_registration_is_pending_and_cannot_sign_in_yet(self):
        response = self.client.post(
            reverse("register_student"),
            self.registration_data(role=Role.ADMIN),
        )

        self.assertRedirects(response, reverse("login"))
        student = User.objects.get(email="ada.student@bazeuniversity.edu.ng")
        self.assertEqual(student.role, Role.STUDENT)
        self.assertFalse(student.is_active)
        self.assertEqual(student.username, student.email)
        profile = student.student_profile
        self.assertEqual(profile.student_number, "BU/26/CS/1001")
        self.assertEqual(profile.student_status, StudentProfile.Status.CURRENT)
        self.assertEqual(profile.registration_status, StudentProfile.RegistrationStatus.PENDING)

        response = self.client.post(
            reverse("login"),
            {"username": student.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "awaiting approval")

    def test_registration_rejects_non_baze_email(self):
        response = self.client.post(
            reverse("register_student"),
            self.registration_data(email="ada@example.com"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ending in @bazeuniversity.edu.ng")
        self.assertFalse(User.objects.filter(username="ada@example.com").exists())

    def test_active_student_can_log_in_with_email_or_student_id(self):
        student = User.objects.create_user(
            username="ada.student@bazeuniversity.edu.ng",
            email="ada.student@bazeuniversity.edu.ng",
            password=self.password,
            role=Role.STUDENT,
        )
        StudentProfile.objects.create(
            user=student,
            student_number="BU/26/CS/1001",
            programme=self.programme,
        )

        for identifier in (student.email, "BU/26/CS/1001"):
            with self.subTest(identifier=identifier):
                response = self.client.post(
                    reverse("login"),
                    {"username": identifier, "password": self.password},
                )
                self.assertRedirects(response, reverse("dashboard"))
                self.client.logout()

    def test_staff_can_log_in_with_baze_email_or_account_username(self):
        staff = User.objects.create_user(
            username="staff.okoro",
            email="okoro@bazeuniversity.edu.ng",
            password=self.password,
            role=Role.SUPERVISOR,
        )

        for identifier in (staff.email, staff.username):
            with self.subTest(identifier=identifier):
                response = self.client.post(
                    reverse("login"),
                    {"username": identifier, "password": self.password},
                )
                self.assertRedirects(response, reverse("dashboard"))
                self.client.logout()

    def test_createsuperuser_is_an_application_admin(self):
        admin = User.objects.create_superuser(
            username="root.admin",
            email="root.admin@bazeuniversity.edu.ng",
            password=self.password,
        )

        self.assertEqual(admin.role, Role.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_admin_can_approve_or_reject_pending_accounts(self):
        admin = User.objects.create_user(
            username="review.admin",
            password=self.password,
            role=Role.ADMIN,
        )
        student = User.objects.create_user(
            username="pending.student@bazeuniversity.edu.ng",
            email="pending.student@bazeuniversity.edu.ng",
            password=self.password,
            role=Role.STUDENT,
            is_active=False,
        )
        StudentProfile.objects.create(
            user=student,
            student_number="BU/26/CS/1002",
            programme=self.programme,
            registration_status=StudentProfile.RegistrationStatus.PENDING,
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("admin_tools"))
        self.assertContains(response, "BU/26/CS/1002")
        self.assertContains(response, student.email)

        response = self.client.post(
            reverse("review_student_registration", args=[student.pk]),
            {"action": "approve"},
        )
        self.assertRedirects(response, reverse("admin_tools"))
        student.refresh_from_db()
        student.student_profile.refresh_from_db()
        self.assertTrue(student.is_active)
        self.assertEqual(student.student_profile.registration_status, StudentProfile.RegistrationStatus.APPROVED)

        rejected = User.objects.create_user(
            username="rejected.student@bazeuniversity.edu.ng",
            email="rejected.student@bazeuniversity.edu.ng",
            password=self.password,
            role=Role.STUDENT,
            is_active=False,
        )
        StudentProfile.objects.create(
            user=rejected,
            student_number="BU/26/CS/1003",
            programme=self.programme,
            registration_status=StudentProfile.RegistrationStatus.PENDING,
        )
        response = self.client.post(
            reverse("review_student_registration", args=[rejected.pk]),
            {"action": "reject"},
        )
        self.assertRedirects(response, reverse("admin_tools"))
        rejected.refresh_from_db()
        rejected.student_profile.refresh_from_db()
        self.assertFalse(rejected.is_active)
        self.assertEqual(rejected.student_profile.registration_status, StudentProfile.RegistrationStatus.REJECTED)

    def test_only_admin_can_review_registrations(self):
        supervisor = User.objects.create_user(
            username="review.supervisor",
            password=self.password,
            role=Role.SUPERVISOR,
        )
        self.client.force_login(supervisor)

        response = self.client.post(
            reverse("review_student_registration", args=[999]),
            {"action": "approve"},
        )

        self.assertEqual(response.status_code, 403)
