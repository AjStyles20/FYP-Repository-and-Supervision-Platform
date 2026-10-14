"""Admins fix students' account mistakes: find them, correct details, reset a password, (de)activate."""

import re

from django.contrib.messages import get_messages
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.audit.models import AuditEvent
from apps.projects.models import Project

from .models import Role, StudentProfile, User

PASSWORD = "Old-pass-2026!"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ManageStudentAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Student Admin Faculty")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.other_department = Department.objects.create(faculty=faculty, name="Information Technology")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.it_programme = Programme.objects.create(department=cls.other_department, name="Information Technology", degree_type="BSc")
        cls.admin = User.objects.create_user("site.admin", password=PASSWORD, role=Role.ADMIN)
        cls.coordinator = User.objects.create_user("coord", password=PASSWORD, role=Role.COORDINATOR, department=cls.department)
        cls.student = cls.make("tolu.ade@bazeuniversity.edu.ng", "BU/23A/CS/5001", first_name="Tolu", last_name="Adde")
        cls.other = cls.make("other@bazeuniversity.edu.ng", "BU/23B/CS/5002")
        cls.pending = cls.make("pending@bazeuniversity.edu.ng", "BU/24C/CS/5003", is_active=False,
                               registration_status=StudentProfile.RegistrationStatus.PENDING)
        cls.with_project = cls.make("working@bazeuniversity.edu.ng", "BU/22A/CS/5004")
        Project.objects.create(student=cls.with_project, title="Seat booking", department=cls.department, programme=cls.programme)
        cls.demo_student = cls.make("demo.kid", "BU/22A/CS/5005", is_demo=True)

    @classmethod
    def make(cls, username, number, registration_status=StudentProfile.RegistrationStatus.APPROVED, **fields):
        email = username if "@" in username else ""
        user = User.objects.create_user(username, email=email, password=PASSWORD, role=Role.STUDENT,
                                        department=cls.department, **fields)
        StudentProfile.objects.create(user=user, student_number=number, programme=cls.programme,
                                      registration_status=registration_status)
        return user

    def url(self, user):
        return reverse("manage_student_account", args=[user.pk])

    def post(self, user, action, **data):
        self.client.force_login(self.admin)
        return self.client.post(self.url(user), {"action": action, **data})

    def details(self, **changes):
        return {"first_name": "Tolu", "last_name": "Adde", "email": "tolu.ade@bazeuniversity.edu.ng",
                "student_number": "BU/23A/CS/5001", "programme": self.programme.pk, **changes}

    def test_only_administrators_open_it_and_only_for_students(self):
        self.client.force_login(self.coordinator)
        self.assertEqual(self.client.get(self.url(self.student)).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url(self.student)).status_code, 200)
        self.assertEqual(self.client.get(self.url(self.coordinator)).status_code, 404)
        self.assertEqual(self.client.get(self.url(self.demo_student)).status_code, 404)  # a real admin, real rows

    def test_admin_tools_finds_a_student_by_name_email_or_id(self):
        self.client.force_login(self.admin)
        for query in ("adde", "TOLU.ADE@", "bu/23a/cs/5001"):
            page = self.client.get(reverse("admin_tools"), {"q": query})
            self.assertContains(page, f'href="{self.url(self.student)}"', msg_prefix=query)
            self.assertNotContains(page, f'href="{self.url(self.other)}"', msg_prefix=query)
        self.assertContains(self.client.get(reverse("admin_tools"), {"q": "nobody"}), "No student matches")

    def test_admin_corrects_name_email_id_and_programme(self):
        response = self.post(self.student, "save", **self.details(
            last_name="Ade", email="Tolu.Ade2@bazeuniversity.edu.ng", student_number="bu/23a/it/5001",
            programme=self.it_programme.pk,
        ))
        self.assertRedirects(response, self.url(self.student))
        self.student.refresh_from_db()
        profile = self.student.student_profile
        self.assertEqual((self.student.last_name, self.student.email, self.student.username),
                         ("Ade", "tolu.ade2@bazeuniversity.edu.ng", "tolu.ade2@bazeuniversity.edu.ng"))
        self.assertEqual((profile.student_number, profile.programme, self.student.department),
                         ("BU/23A/IT/5001", self.it_programme, self.other_department))
        details = AuditEvent.objects.get(action="account.student_updated").details
        self.assertEqual(set(details), {"last_name", "email", "student_number", "programme"})
        self.assertEqual([message.to for message in mail.outbox], [["tolu.ade2@bazeuniversity.edu.ng"]])

        self.client.logout()
        # The corrected Baze email signs in; the student ID does not (D-41).
        for identifier, expected in (("tolu.ade2@bazeuniversity.edu.ng", 302), ("BU/23A/IT/5001", 200)):
            self.assertEqual(self.client.post(reverse("login"), {"username": identifier, "password": PASSWORD}).status_code, expected)
            self.client.logout()

    def test_wrong_corrections_are_refused_and_nothing_changes(self):
        cases = (
            ({"student_number": "5001"}, "full student ID as it appears"),
            ({"student_number": "BU/23B/CS/5002"}, "Another student already has this student ID"),
            ({"email": "other@bazeuniversity.edu.ng"}, "Another account already uses this email address"),
            ({"email": "tolu@gmail.com"}, "Use a Baze email address"),
        )
        for changes, message in cases:
            with self.subTest(message):
                response = self.post(self.student, "save", **self.details(**changes))
                self.assertContains(response, message)
        response = self.post(self.with_project, "save", first_name="", last_name="", email="working@bazeuniversity.edu.ng",
                             student_number="BU/22A/CS/5004", programme=self.it_programme.pk)
        self.assertContains(response, "already has a project, so their programme cannot be changed")
        self.student.refresh_from_db()
        self.assertEqual((self.student.email, self.student.student_profile.student_number),
                         ("tolu.ade@bazeuniversity.edu.ng", "BU/23A/CS/5001"))
        self.assertFalse(AuditEvent.objects.filter(action="account.student_updated").exists())

    def test_a_forgotten_password_is_reset_and_must_be_changed_at_sign_in(self):
        response = self.post(self.student, "reset_password")
        self.assertEqual(response["Cache-Control"], "no-store")
        temporary = re.search(r"data-temporary-password>([^<]+)<", response.content.decode()).group(1)
        self.assertTrue(AuditEvent.objects.filter(action="account.password_reset").exists())

        self.client.logout()
        self.assertEqual(self.client.post(reverse("login"), {"username": self.student.email, "password": PASSWORD}).status_code, 200)
        self.client.post(reverse("login"), {"username": self.student.email, "password": temporary})
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("password_change"))

    def test_deactivate_and_reactivate_but_never_bypass_approval(self):
        self.post(self.student, "deactivate")
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.post(self.student, "reactivate")
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

        response = self.post(self.pending, "reactivate")
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_active)
        self.assertTrue(any("This registration has not been approved" in str(m) for m in get_messages(response.wsgi_request)))
