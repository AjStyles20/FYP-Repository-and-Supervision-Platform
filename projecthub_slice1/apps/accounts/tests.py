import shutil
import tempfile
from collections import Counter
from io import StringIO
from pathlib import Path

from django.contrib.messages import get_messages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.audit.models import AuditEvent
from apps.accounts.models import STAFF_ROLES, Role, StudentProfile, SupervisorProfile, User
from apps.projects.models import (
    ArchivedProject,
    Project,
    ProjectApprovalDecision,
    ProjectDocument,
    ProjectMilestone,
    ProjectStage,
    ProjectSupervisorAssignment,
)
from apps.supervision.models import Announcement, Notification, NotificationKind, SharedResource, SupervisionMeeting


# seed_demo writes demo report files; keep them out of the real media folder during tests.
TEST_MEDIA = tempfile.mkdtemp(prefix="projecthub-test-media-")


def tearDownModule():
    shutil.rmtree(TEST_MEDIA, ignore_errors=True)


def run(*args, **kwargs):
    """Django's test runner always sets DEBUG=False, so seeding in tests needs --force."""
    if args and args[0] == "seed_demo":
        kwargs.setdefault("force", True)
    call_command(*args, stdout=StringIO(), stderr=StringIO(), **kwargs)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
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


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class SeedAndPurgeTests(TestCase):
    def test_seed_creates_expected_demo_data(self):
        run("seed_demo")
        self.assertEqual(User.objects.filter(is_demo=True, role=Role.STUDENT).count(), 21)
        self.assertEqual(User.objects.filter(is_demo=True, role=Role.SUPERVISOR).count(), 6)
        self.assertEqual(SupervisorProfile.objects.count(), 6)
        self.assertEqual(StudentProfile.objects.count(), 21)
        self.assertEqual(Faculty.objects.filter(is_demo=True).count(), 1)
        self.assertEqual(Department.objects.filter(is_demo=True).count(), 2)
        self.assertEqual(User.objects.get(username="demo.amina").email, "amina@bazeuniversity.edu.ng")
        self.assertEqual(Project.objects.filter(is_demo=True).count(), 21)
        # One project is deliberately unassigned; one was reassigned, so its first row is closed.
        self.assertEqual(ProjectSupervisorAssignment.objects.filter(ended_at__isnull=True).count(), 20)
        self.assertEqual(ArchivedProject.objects.filter(is_demo=True).count(), 4)

    def test_seed_tells_the_demo_story(self):
        run("seed_demo")
        stages = Counter(Project.objects.filter(is_demo=True).values_list("stage", flat=True))
        self.assertEqual(set(stages), set(ProjectStage.values), "every stage has at least one project")
        self.assertEqual(stages[ProjectStage.COMPLETED], 4)
        for department in Department.objects.filter(is_demo=True):
            methods = set(SupervisorProfile.objects.filter(user__department=department).values_list("approval_method", flat=True))
            self.assertEqual(methods, {"topic_only", "literature_review", "working_project"}, department.name)
        archived = ArchivedProject.objects.filter(is_demo=True)
        self.assertTrue(all(project.gap_summary for project in archived))
        statuses = Counter(archived.values_list("student__student_profile__student_status", flat=True))
        self.assertEqual(statuses, {StudentProfile.Status.GRADUATED: 2, StudentProfile.Status.FYP_COMPLETED: 2})
        self.assertTrue(archived.filter(previous_supervisors__isnull=False).exists())
        # Every project moved through the real workflow, so each stage change has a history row.
        for project in Project.objects.filter(is_demo=True):
            self.assertEqual(project.status_events.count(), project.stage_position, project.title)

    def test_seed_includes_a_visible_append_only_decision_history(self):
        run("seed_demo")
        project = Project.objects.get(title="Course Registration Clash Detector")
        decisions = list(project.approval_decisions.values_list("decision", "proposed_title"))
        self.assertEqual(decisions, [
            ("rejected", "Timetable Clash Checker for the Whole University"),
            ("accepted_with_changes", "Course Registration Clash Detector"),
            ("", "Course Registration Clash Detector"),
        ])
        self.assertEqual(ProjectApprovalDecision.objects.filter(project=project).count(), 3)
        self.client.force_login(User.objects.get(username="demo.adaeze"))
        page = self.client.get(reverse("project_workflow", args=[project.pk]))
        self.assertContains(page, "Approval decisions")
        self.assertContains(page, "Timetable Clash Checker for the Whole University")
        self.assertContains(page, "The scope is too broad")

    def test_seed_shows_every_health_band(self):
        from apps.projects.services.health import health_score

        run("seed_demo")
        scores = {
            project.student.username: health_score(project)
            for project in Project.objects.filter(is_demo=True, archived=False).select_related("student")
        }
        self.assertEqual({name: (scores[name].score, scores[name].band) for name in
                          ("demo.amina", "demo.yemi", "demo.sadiq", "demo.chinedu")}, {
            "demo.amina": (75, "at_risk"), "demo.yemi": (50, "watch"),
            "demo.sadiq": (39, "watch"), "demo.chinedu": (20, "on_track"),
        })
        self.assertEqual({health.band for health in scores.values() if health}, {"on_track", "watch", "at_risk"})
        self.assertTrue(ProjectMilestone.objects.filter(project__student__username="demo.amina", done=False,
                                                        due_date__lt=timezone.localdate()).exists())

    def test_seed_has_an_archived_project_similar_to_a_running_topic(self):
        from apps.projects.services.similarity import similar_archived_projects

        run("seed_demo")
        running = Project.objects.get(title="Campus Shuttle Delay Tracker")
        matches = similar_archived_projects(running.title, running.description)
        self.assertEqual([match["title"] for match in matches], ["Campus Shuttle Tracker"])
        self.assertGreaterEqual(matches[0]["score"], 0.35)

    def test_seed_upgrades_an_older_demo_database_without_duplicates(self):
        run("seed_demo")
        before = (Announcement.objects.count(), SharedResource.objects.count())
        # An older seed had no milestones and no back-dated history.
        ProjectMilestone.objects.all().delete()
        run("seed_demo")
        self.assertEqual((Announcement.objects.count(), SharedResource.objects.count()), before)
        self.assertEqual(ProjectMilestone.objects.count(), 10)

    def test_seed_is_repeatable(self):
        run("seed_demo")
        before = (User.objects.count(), Project.objects.count(), ProjectApprovalDecision.objects.count())
        run("seed_demo")
        self.assertEqual((User.objects.count(), Project.objects.count(), ProjectApprovalDecision.objects.count()), before)
        self.assertEqual(ProjectSupervisorAssignment.objects.filter(ended_at__isnull=True).count(), 20)
        self.assertEqual(ProjectMilestone.objects.count(), 10)

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
        demo_files = [Path(document.file.path) for document in ProjectDocument.objects.filter(is_demo=True)]
        self.assertTrue(demo_files and all(path.exists() for path in demo_files))
        with self.captureOnCommitCallbacks(execute=True):
            run("purge_demo")
        self.assertFalse(any(path.exists() for path in demo_files))
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


class SummaryApiTests(TestCase):
    """/api/summary/: counters for admins and coordinators, only the unread count for other roles, 401 signed out."""

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Summary Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Summary Department")
        other = Department.objects.create(faculty=faculty, name="Other Summary Department")
        programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        other_programme = Programme.objects.create(department=other, name="Law", degree_type="LLB")
        cls.admin = User.objects.create(username="summary.admin", role=Role.ADMIN)
        cls.coordinator = User.objects.create(username="summary.coordinator", role=Role.COORDINATOR, department=cls.department)
        cls.supervisor = User.objects.create(username="summary.supervisor", role=Role.SUPERVISOR, department=cls.department)
        cls.hod = User.objects.create(username="summary.hod", role=Role.HOD, department=cls.department)
        cls.student = User.objects.create(
            username="kemi.private@bazeuniversity.edu.ng", email="kemi.private@bazeuniversity.edu.ng",
            first_name="Kemi", last_name="Private", role=Role.STUDENT,
        )
        StudentProfile.objects.create(
            user=cls.student, student_number="BU/26/SUM/1", programme=programme,
            registration_status=StudentProfile.RegistrationStatus.PENDING,
        )
        for title, stage, supervisor, dept, prog in (
            ("Unassigned topic", ProjectStage.PROPOSED, None, cls.department, programme),
            ("Form to log", ProjectStage.SUPERVISOR_ACCEPTED, cls.supervisor, cls.department, programme),
            ("Other department", ProjectStage.SUBMITTED, None, other, other_programme),
        ):
            Project.objects.create(
                student=User.objects.create(username=f"summary.{title}", role=Role.STUDENT), title=title,
                stage=stage, supervisor=supervisor, department=dept, programme=prog,
            )
        Notification.objects.create(
            recipient=cls.admin, kind=NotificationKind.PENDING_REGISTRATION, object_type="accounts.User",
            object_id=str(cls.student.pk), title="Registration waiting",
        )

    def _get(self, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(reverse("api_summary"))

    def test_admin_gets_the_admin_counters_and_unread_alerts(self):
        response = self._get(self.admin)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        body = response.json()
        self.assertEqual(set(body), {"role", "counters", "unread_notifications", "generated_at"})
        self.assertEqual(body["role"], "admin")
        self.assertEqual(body["counters"], {
            "pending_count": 1,
            "student_count": User.objects.filter(role=Role.STUDENT, is_active=True, is_demo=False).count(),
            "staff_count": 3,
            "programme_count": 2,
        })
        self.assertEqual(body["unread_notifications"], 1)

    def test_response_contains_numbers_only_and_no_personal_data(self):
        for user in (self.admin, self.coordinator):
            response = self._get(user)
            for private in ("kemi", "Private", "@", "BU/26", "summary."):
                self.assertNotIn(private, response.content.decode(), f"{user.username}: {private}")
            body = response.json()
            self.assertTrue(all(isinstance(value, int) for value in body["counters"].values()))
            self.assertIsInstance(body["unread_notifications"], int)

    def test_coordinator_gets_only_their_department_counters(self):
        body = self._get(self.coordinator).json()

        self.assertEqual(body["role"], "coordinator")
        self.assertEqual(body["counters"], {"active_count": 2, "unassigned_count": 1, "approval_count": 1, "defence_count": 0})
        self.assertEqual(body["unread_notifications"], 0)

    def test_counters_match_the_portal_page(self):
        for user in (self.admin, self.coordinator):
            counters = self._get(user).json()["counters"]
            page = self.client.get(reverse("dashboard"))
            for name, value in counters.items():
                self.assertEqual(page.context[name], value, f"{user.username}: {name}")
                self.assertContains(page, f'data-counter="{name}">{value}<')

    def test_other_roles_get_only_their_own_unread_count(self):
        Notification.objects.create(
            recipient=self.supervisor, kind=NotificationKind.AT_RISK_PROJECT, object_type="projects.Project",
            object_id="1", title="Project at risk",
        )
        for user, unread in ((self.supervisor, 1), (self.hod, 0), (self.student, 0)):
            response = self._get(user)
            self.assertEqual(response.status_code, 200, user.username)
            body = response.json()
            self.assertEqual(set(body), {"role", "unread_notifications", "generated_at"}, user.username)
            self.assertEqual((body["role"], body["unread_notifications"]), (user.role, unread))
            self.assertNotIn("Project at risk", response.content.decode())

    def test_signed_out_gets_401_json_not_a_login_redirect(self):
        response = self._get()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Sign in required."})

    def test_only_get_is_allowed(self):
        self.client.force_login(self.admin)

        self.assertEqual(self.client.post(reverse("api_summary")).status_code, 405)

    def test_polling_script_is_loaded_for_every_signed_in_user(self):
        self.assertNotContains(self.client.get(reverse("login")), "js/live-counters.js")
        for user in (self.admin, self.coordinator, self.supervisor, self.hod, self.student):
            self.client.force_login(user)
            self.assertContains(self.client.get(reverse("announcements")), "js/live-counters.js", msg_prefix=user.username)


class StaffAccountTests(TestCase):
    """Staff accounts are created by an admin only, with a one-time temporary password."""

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Staff Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Staff Department")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.admin = User.objects.create(username="staff.admin", role=Role.ADMIN)
        cls.supervisor = User.objects.create(username="staff.supervisor", role=Role.SUPERVISOR, department=cls.department)

    def _create(self, **overrides):
        data = {
            "first_name": "Ngozi", "last_name": "Eze", "email": "Ngozi.Eze@bazeuniversity.edu.ng",
            "role": Role.SUPERVISOR, "department": self.department.pk, "title": "Dr.",
        }
        data.update(overrides)
        self.client.force_login(self.admin)
        return self.client.post(reverse("add_staff_account"), data)

    def test_only_admins_can_open_the_page(self):
        url = reverse("add_staff_account")
        self.assertIn("/login/", self.client.get(url)["Location"])
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"role": Role.ADMIN}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_admin_creates_a_supervisor_with_a_one_time_password(self):
        response = self._create()

        user = User.objects.get(username="ngozi.eze@bazeuniversity.edu.ng")
        self.assertEqual((user.role, user.department, user.email), (Role.SUPERVISOR, self.department, user.username))
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.is_active)
        self.assertEqual(user.supervisor_profile.title, "Dr.")
        password = response.context["temporary_password"]
        self.assertGreaterEqual(len(password), 16)
        self.assertTrue(user.check_password(password))
        self.assertContains(response, password)
        self.assertEqual(response["Cache-Control"], "no-store")

        event = AuditEvent.objects.get(action="account.staff_created")
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.details, {"role": "supervisor", "department": "Staff Department", "can_assign_supervisors": False})
        self.assertNotIn(password, f"{event.summary} {event.details}")

    def test_every_account_gets_a_different_password(self):
        first = self._create().context["temporary_password"]
        second = self._create(email="other.person@bazeuniversity.edu.ng").context["temporary_password"]
        self.assertNotEqual(first, second)

    def test_admin_role_needs_no_department_and_never_gets_allocation_rights(self):
        self._create(email="new.admin@bazeuniversity.edu.ng", role=Role.ADMIN, department="", can_assign_supervisors="on")

        user = User.objects.get(username="new.admin@bazeuniversity.edu.ng")
        self.assertEqual((user.role, user.department, user.can_assign_supervisors), (Role.ADMIN, None, False))
        self.assertFalse(hasattr(user, "supervisor_profile"))

    def test_validation(self):
        cases = {
            "non-Baze email": ({"email": "someone@gmail.com"}, "email"),
            "duplicate email": ({"email": "STAFF.SUPERVISOR@bazeuniversity.edu.ng"}, None),
            "missing department": ({"department": ""}, "department"),
            "student role": ({"role": Role.STUDENT}, "role"),
        }
        User.objects.filter(pk=self.supervisor.pk).update(email="staff.supervisor@bazeuniversity.edu.ng")
        for label, (overrides, field) in cases.items():
            response = self._create(**overrides)
            self.assertEqual(response.status_code, 200, label)
            self.assertTrue(response.context["form"].errors, label)
            if field:
                self.assertIn(field, response.context["form"].errors, label)
        self.assertEqual(User.objects.filter(role__in=STAFF_ROLES).count(), 2)

    def test_new_staff_must_choose_a_password_before_using_the_site(self):
        password = self._create().context["temporary_password"]
        self.client.logout()
        self.assertTrue(self.client.login(username="ngozi.eze@bazeuniversity.edu.ng", password=password))

        for url in (reverse("dashboard"), reverse("repository"), reverse("api_summary")):
            self.assertRedirects(self.client.get(url), reverse("password_change"), fetch_redirect_response=False)
        page = self.client.get(reverse("password_change"))
        self.assertContains(page, "Choose your password")

        response = self.client.post(reverse("password_change"), {
            "old_password": password, "new_password1": "Supervise-Baze-2026!", "new_password2": "Supervise-Baze-2026!",
        })

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        user = User.objects.get(username="ngozi.eze@bazeuniversity.edu.ng")
        self.assertFalse(user.must_change_password)
        self.assertTrue(user.check_password("Supervise-Baze-2026!"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertTrue(AuditEvent.objects.filter(action="account.password_set", actor=user).exists())

    def test_student_sign_up_cannot_choose_a_role_and_points_staff_elsewhere(self):
        page = self.client.get(reverse("register_student"))
        self.assertContains(page, "Staff?")
        self.assertNotContains(page, 'name="role"')

        self.client.post(reverse("register_student"), {
            "first_name": "Sneaky", "last_name": "Person", "email": "sneaky@bazeuniversity.edu.ng",
            "student_number": "BU/26/CS/7777", "programme": self.programme.pk, "student_status": "current",
            "password1": "Long-enough-pass-77", "password2": "Long-enough-pass-77", "role": Role.ADMIN,
        })

        user = User.objects.get(username="sneaky@bazeuniversity.edu.ng")
        self.assertEqual((user.role, user.is_active), (Role.STUDENT, False))

    def test_admin_only_fields_are_marked_for_hiding_on_both_forms(self):
        self.client.force_login(self.admin)
        for url in (reverse("add_staff_account"), reverse("manage_staff_account", args=[self.supervisor.pk])):
            page = self.client.get(url).content.decode()
            self.assertEqual(page.count("data-staff-only"), 3, url)
            self.assertIn("js/staff-form.js", page, url)

    def test_admin_tools_lists_staff_with_their_status(self):
        self._create()
        self.client.force_login(self.admin)

        response = self.client.get(reverse("admin_tools"))

        self.assertContains(response, "Add staff account")
        self.assertContains(response, "ngozi.eze@bazeuniversity.edu.ng")
        self.assertContains(response, "Waiting for first sign-in")


class ManageStaffAccountTests(TestCase):
    """Admins edit, deactivate, reactivate and reset staff accounts, without locking themselves out."""

    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Manage Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Manage Department")
        cls.other_department = Department.objects.create(faculty=faculty, name="Other Manage Department")
        cls.admin = User.objects.create_user("manage.admin", password="Admin-pass-2026!", role=Role.ADMIN)
        cls.supervisor = User.objects.create_user(
            "lecturer@bazeuniversity.edu.ng", email="lecturer@bazeuniversity.edu.ng", password="Old-pass-2026!",
            first_name="Kemi", last_name="Lecturer", role=Role.SUPERVISOR, department=cls.department,
        )
        SupervisorProfile.objects.create(user=cls.supervisor, title="Mr.")
        cls.student = User.objects.create(username="manage.student", role=Role.STUDENT)

    def _post(self, user, action, **data):
        self.client.force_login(self.admin)
        return self.client.post(reverse("manage_staff_account", args=[user.pk]), {"action": action, **data})

    def _details(self, **overrides):
        data = {"first_name": "Kemi", "last_name": "Lecturer", "role": Role.SUPERVISOR,
                "department": self.department.pk, "title": "Mr."}
        data.update(overrides)
        return data

    def test_only_admins_and_only_staff_accounts(self):
        url = reverse("manage_staff_account", args=[self.supervisor.pk])
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(reverse("manage_staff_account", args=[self.student.pk])).status_code, 404)

    def test_promote_to_coordinator_in_another_department_is_saved_and_audited(self):
        response = self._post(self.supervisor, "save", **self._details(
            role=Role.COORDINATOR, department=self.other_department.pk, title="Dr.", can_assign_supervisors="on",
        ))

        self.assertRedirects(response, reverse("manage_staff_account", args=[self.supervisor.pk]))
        self.assertEqual([str(m) for m in get_messages(response.wsgi_request)], ["Saved the changes to Kemi Lecturer."])
        self.supervisor.refresh_from_db()
        self.assertEqual((self.supervisor.role, self.supervisor.department, self.supervisor.can_assign_supervisors),
                         (Role.COORDINATOR, self.other_department, True))
        self.assertEqual(self.supervisor.supervisor_profile.title, "Dr.")
        event = AuditEvent.objects.get(action="account.staff_updated")
        self.assertEqual(set(event.details), {"role", "department", "can_assign_supervisors", "title"})
        self.assertEqual(event.details["role"], {"from": "supervisor", "to": "coordinator"})

    def test_deactivated_staff_cannot_sign_in_and_reactivation_restores_it(self):
        self._post(self.supervisor, "deactivate")
        self.supervisor.refresh_from_db()
        self.assertFalse(self.supervisor.is_active)
        self.client.logout()
        self.assertFalse(self.client.login(username="lecturer@bazeuniversity.edu.ng", password="Old-pass-2026!"))

        self._post(self.supervisor, "reactivate")
        self.client.logout()
        self.assertTrue(self.client.login(username="lecturer@bazeuniversity.edu.ng", password="Old-pass-2026!"))
        self.assertEqual(
            list(AuditEvent.objects.filter(object_id=str(self.supervisor.pk)).values_list("action", flat=True).order_by("pk")),
            ["account.staff_deactivated", "account.staff_reactivated"],
        )

    def test_deactivation_ends_an_open_session(self):
        session = self.client_class()
        session.force_login(self.supervisor)
        self.assertEqual(session.get(reverse("dashboard")).status_code, 200)

        self._post(self.supervisor, "deactivate")

        self.assertIn("/login/", session.get(reverse("dashboard"))["Location"])

    def test_reset_password_shows_a_new_one_time_password(self):
        response = self._post(self.supervisor, "reset_password")

        password = response.context["temporary_password"]
        self.assertContains(response, "Password reset")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.supervisor.refresh_from_db()
        self.assertTrue(self.supervisor.check_password(password))
        self.assertFalse(self.supervisor.check_password("Old-pass-2026!"))
        self.assertTrue(self.supervisor.must_change_password)
        event = AuditEvent.objects.get(action="account.password_reset")
        self.assertNotIn(password, f"{event.summary} {event.details}")

    def test_saved_message_uses_the_new_name(self):
        self._post(self.supervisor, "save", **self._details(first_name="Adaeze", last_name="Okafor"))
        page = self.client.get(reverse("manage_staff_account", args=[self.supervisor.pk]))
        self.assertContains(page, "Saved the changes to Adaeze Okafor.")

    def test_an_admin_cannot_lock_themselves_out(self):
        self._post(self.admin, "deactivate")
        response = self._post(self.admin, "save", first_name="", last_name="Admin", role=Role.SUPERVISOR,
                              department=self.department.pk)
        self.admin.refresh_from_db()
        self.assertEqual((self.admin.is_active, self.admin.role), (True, Role.ADMIN))
        self.assertIn("role", response.context["form"].errors)

    def test_the_last_active_admin_cannot_be_removed_by_another_admin(self):
        other = User.objects.create(username="other.admin", role=Role.ADMIN)
        User.objects.filter(pk=self.admin.pk).update(is_active=True)
        # With two admins, one may deactivate the other ...
        self._post(other, "deactivate")
        other.refresh_from_db()
        self.assertFalse(other.is_active)
        # ... but a second admin account that is the only *active* one stays protected.
        User.objects.filter(pk=other.pk).update(is_active=True)
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        self.client.force_login(other)
        self.client.post(reverse("manage_staff_account", args=[other.pk]), {"action": "deactivate"})
        other.refresh_from_db()
        self.assertTrue(other.is_active)
