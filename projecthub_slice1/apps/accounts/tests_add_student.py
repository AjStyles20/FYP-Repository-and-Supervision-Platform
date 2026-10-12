"""D-28: students do not register themselves; an administrator or their coordinator creates the account."""

import re

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.audit.models import AuditEvent

from .models import Role, StudentProfile, User


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AddStudentAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Add Student Faculty")
        cls.cs = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.cyber = Department.objects.create(faculty=faculty, name="Cyber Security")
        cls.cs_programme = Programme.objects.create(department=cls.cs, name="Computer Science", degree_type="BSc")
        cls.cyber_programme = Programme.objects.create(department=cls.cyber, name="Cyber Security", degree_type="BSc")
        cls.admin = User.objects.create(username="admin.user", role=Role.ADMIN)
        cls.coordinator = User.objects.create(username="coord", role=Role.COORDINATOR, department=cls.cs, can_assign_supervisors=True)
        cls.supervisor = User.objects.create(username="sup", role=Role.SUPERVISOR, department=cls.cs)
        cls.hod = User.objects.create(username="hod", role=Role.HOD, department=cls.cs)

    def data(self, **changes):
        return {"first_name": "Tolu", "last_name": "Ade", "email": "Tolu.Ade@bazeuniversity.edu.ng",
                "student_number": "bu/23a/cs/5001", "programme": self.cs_programme.pk, "student_status": "current", **changes}

    def add(self, creator, **changes):
        self.client.force_login(creator)
        return self.client.post(reverse("add_student_account"), self.data(**changes))

    def test_self_registration_is_closed_by_default(self):
        page = self.client.get(reverse("register_student"))
        self.assertContains(page, "Student accounts are created by your department")
        self.assertNotContains(page, 'name="password1"')
        self.client.post(reverse("register_student"), {"first_name": "Eve", "email": "eve@bazeuniversity.edu.ng"})
        self.assertFalse(User.objects.filter(role=Role.STUDENT).exists())
        login = self.client.get(reverse("login"))
        self.assertNotContains(login, f'href="{reverse("register_student")}"')
        self.assertContains(login, "created by your department's FYP coordinator")

    def test_an_administrator_adds_a_student_who_must_choose_a_password(self):
        response = self.add(self.admin, programme=self.cyber_programme.pk)
        self.assertEqual(response["Cache-Control"], "no-store")
        temporary = re.search(r"data-temporary-password>([^<]+)<", response.content.decode()).group(1)

        student = User.objects.get(email="tolu.ade@bazeuniversity.edu.ng")
        profile = student.student_profile
        self.assertEqual((student.role, student.is_active, student.must_change_password, student.department),
                         (Role.STUDENT, True, True, self.cyber))
        self.assertEqual((profile.student_number, profile.registration_status),
                         ("BU/23A/CS/5001", StudentProfile.RegistrationStatus.APPROVED))
        event = AuditEvent.objects.get(action="account.student_created")
        self.assertEqual(event.actor, self.admin)
        self.assertNotIn(temporary, str(event.details) + event.summary)

        self.client.logout()
        self.client.post(reverse("login"), {"username": "BU/23A/CS/5001", "password": temporary})
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("password_change"))

    def test_a_coordinator_adds_students_of_their_own_department_only(self):
        self.client.force_login(self.coordinator)
        choices = list(self.client.get(reverse("add_student_account")).context["form"].fields["programme"].queryset)
        self.assertEqual(choices, [self.cs_programme])

        refused = self.add(self.coordinator, programme=self.cyber_programme.pk)
        self.assertContains(refused, "Select a valid choice")
        self.add(self.coordinator)
        student = User.objects.get(email="tolu.ade@bazeuniversity.edu.ng")
        waiting = [row["student"] for row in self.client.get(reverse("supervisor_assignments")).context["student_rows"]]
        self.assertIn(student, waiting)  # ready to be given a supervisor

    def test_other_roles_cannot_add_students(self):
        for user in (self.supervisor, self.hod):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("add_student_account")).status_code, 403, user.role)
        homeless = User.objects.create(username="coord2", role=Role.COORDINATOR)
        self.client.force_login(homeless)
        self.assertEqual(self.client.get(reverse("add_student_account")).status_code, 403)

    def test_the_same_checks_as_registration(self):
        self.add(self.admin)
        cases = (
            ({"email": "tolu.ade@bazeuniversity.edu.ng", "student_number": "BU/23A/CS/5002"}, "An account already exists with this email address"),
            ({"email": "second@bazeuniversity.edu.ng", "student_number": "BU/23A/CS/5001"}, "Another student already has this student ID"),
            ({"email": "x@gmail.com", "student_number": "BU/23A/CS/5003"}, "Use a Baze email address"),
            ({"email": "y@bazeuniversity.edu.ng", "student_number": "5003"}, "full student ID as it appears"),
        )
        for changes, message in cases:
            with self.subTest(message):
                self.assertContains(self.add(self.admin, **changes), message)
        self.assertEqual(User.objects.filter(role=Role.STUDENT).count(), 1)

    def test_menus_link_to_add_student(self):
        self.client.force_login(self.coordinator)
        self.assertContains(self.client.get(reverse("supervisor_assignments")), f'href="{reverse("add_student_account")}"')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("admin_tools")), f'href="{reverse("add_student_account")}"')
