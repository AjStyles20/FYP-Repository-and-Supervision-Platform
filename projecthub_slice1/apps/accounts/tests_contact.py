"""Contact details: each person edits their own personal email and phone, and chooses who sees each."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.projects.models import Project, ProjectStage

from .models import ContactVisibility, Role, StudentProfile, User


class ContactDetailsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Contact Faculty")
        department = Department.objects.create(faculty=faculty, name="Computer Science")
        programme = Programme.objects.create(department=department, name="Computer Science", degree_type="BSc")
        cls.student = User.objects.create(username="ada@bazeuniversity.edu.ng", email="ada@bazeuniversity.edu.ng",
                                          role=Role.STUDENT, first_name="Ada")
        StudentProfile.objects.create(user=cls.student, student_number="BU/22A/CS/1001", programme=programme)
        cls.supervisor = User.objects.create(username="okoro@bazeuniversity.edu.ng", email="okoro@bazeuniversity.edu.ng",
                                             role=Role.SUPERVISOR, department=department)
        cls.other_student = User.objects.create(username="reader", role=Role.STUDENT)
        cls.other_staff = User.objects.create(username="hod", role=Role.HOD, department=department)
        cls.project = Project.objects.create(student=cls.student, title="Library Seat Booking", stage=ProjectStage.IN_PROGRESS,
                                             department=department, programme=programme, supervisor=cls.supervisor)

    def _save(self, user, **data):
        self.client.force_login(user)
        return self.client.post(reverse("my_contact"), {
            "personal_email": "", "personal_email_visibility": "hidden", "phone": "", "phone_visibility": "hidden", **data,
        })

    def test_students_and_staff_edit_their_own_details_but_not_their_baze_email(self):
        for user in (self.student, self.supervisor):
            response = self._save(user, personal_email="Me.Personal@Gmail.com", personal_email_visibility="signed_in",
                                  phone="+234  803 123 4567", phone_visibility="staff", email="changed@example.com")
            self.assertRedirects(response, reverse("my_contact"))
            user.refresh_from_db()
            self.assertEqual((user.personal_email, user.phone), ("me.personal@gmail.com", "+234 803 123 4567"))
            self.assertEqual((user.personal_email_visibility, user.phone_visibility), ("signed_in", "staff"))
            self.assertTrue(user.email.endswith("@bazeuniversity.edu.ng"))

    def test_a_baze_address_or_a_bad_phone_is_refused(self):
        response = self._save(self.student, personal_email="ada@bazeuniversity.edu.ng", phone="call me")
        self.assertContains(response, "Use a personal address here")
        self.assertContains(response, "Enter a phone number such as")
        self.student.refresh_from_db()
        self.assertEqual((self.student.personal_email, self.student.phone), ("", ""))

    def test_the_page_needs_sign_in_and_is_linked_from_the_menu(self):
        self.assertRedirects(self.client.get(reverse("my_contact")), f"{reverse('login')}?next={reverse('my_contact')}")
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("dashboard"), follow=True), f'href="{reverse("my_contact")}"')

    def test_each_detail_is_shown_only_to_the_people_its_owner_chose(self):
        User.objects.filter(pk=self.student.pk).update(
            personal_email="ada.home@gmail.com", personal_email_visibility=ContactVisibility.SIGNED_IN,
            phone="+234 803 000 0001", phone_visibility=ContactVisibility.STAFF,
        )
        User.objects.filter(pk=self.supervisor.pk).update(phone="+234 803 000 0002", phone_visibility=ContactVisibility.HIDDEN)
        page_url = reverse("current_project_detail", args=[self.project.pk])
        for viewer, sees_email, sees_phone in ((self.other_student, True, False), (self.other_staff, True, True),
                                               (self.student, True, True)):
            self.client.force_login(viewer)
            page = self.client.get(page_url).content.decode()
            self.assertEqual("ada.home@gmail.com" in page, sees_email, viewer.username)
            self.assertEqual("+234 803 000 0001" in page, sees_phone, viewer.username)
            self.assertNotIn("+234 803 000 0002", page)  # the supervisor kept their phone to themselves

    def test_a_supervisors_shared_contact_appears_on_the_project_page(self):
        User.objects.filter(pk=self.supervisor.pk).update(personal_email="okoro.home@gmail.com",
                                                          personal_email_visibility=ContactVisibility.SIGNED_IN)
        self.client.force_login(self.other_student)
        page = self.client.get(reverse("current_project_detail", args=[self.project.pk]))
        self.assertContains(page, "Supervisor contact")
        self.assertContains(page, 'href="mailto:okoro.home@gmail.com"')

    def test_a_current_student_without_a_personal_email_is_reminded(self):
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("student_portal")), "Add a personal email")


class ContactMigrationTests(TransactionTestCase):
    """Migration 0009 copies an existing student contact email and keeps its consent."""

    before = [("accounts", "0008_user_must_change_password")]

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.before)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_student_contact_emails_move_to_the_user_with_their_consent(self):
        old_apps = self.executor.loader.project_state(self.before).apps
        OldUser = old_apps.get_model("accounts", "User")
        OldProfile = old_apps.get_model("accounts", "StudentProfile")
        # The academics tables are not rolled back, so their rows are made with the current models.
        department = Department.objects.create(faculty=Faculty.objects.create(name="Migration Faculty"), name="CS")
        programme_id = Programme.objects.create(department=department, name="CS", degree_type="BSc").pk
        shared = OldUser.objects.create(username="shared", role="student")
        private = OldUser.objects.create(username="private", role="student")
        OldProfile.objects.create(user=shared, student_number="M1", programme_id=programme_id, contact_email="s@gmail.com", contact_consent=True)
        OldProfile.objects.create(user=private, student_number="M2", programme_id=programme_id, contact_email="p@gmail.com", contact_consent=False)

        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

        self.assertEqual(
            sorted(User.objects.filter(username__in=("shared", "private")).values_list("username", "personal_email", "personal_email_visibility")),
            [("private", "p@gmail.com", "hidden"), ("shared", "s@gmail.com", "signed_in")],
        )
