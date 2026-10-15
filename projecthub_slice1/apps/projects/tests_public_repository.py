"""The public showcase (D-42): visitors who are not logged in may browse completed projects as
summaries. Running topics, files and student identification numbers stay login-only, and a
student's contact details appear only if the student made their personal email public."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.forms import ContactDetailsForm
from apps.accounts.models import ContactVisibility, Role, StudentProfile, User

from .models import ArchivedProject, Project, ProjectDocument


@override_settings(PUBLIC_REPOSITORY=True)
class PublicShowcaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Showcase Faculty")
        department = Department.objects.create(faculty=faculty, name="Computer Science")
        programme = Programme.objects.create(department=department, name="Computer Science", degree_type="Bachelor of Science")
        cls.supervisor = User.objects.create(username="show.supervisor", first_name="Julius", last_name="Makinde",
                                             role=Role.SUPERVISOR, department=department)
        cls.student = User.objects.create(username="show.student", first_name="Daniel", last_name="Akpan", role=Role.STUDENT,
                                          personal_email="daniel@example.com", personal_email_visibility=ContactVisibility.PUBLIC,
                                          phone="+234 800 000 0101", phone_visibility=ContactVisibility.SIGNED_IN)
        StudentProfile.objects.create(user=cls.student, student_number="BU/21A/CS/4417", programme=programme,
                                      student_status=StudentProfile.Status.FYP_COMPLETED)
        cls.archived = ArchivedProject.objects.create(
            title="Early Warning System for Student Performance", description="Predicts students at risk.",
            year=2025, department=department, programme=programme, student=cls.student, supervisor=cls.supervisor,
            gap_summary="Validate across the whole university.",
        )
        cls.running_student = User.objects.create(username="show.running", role=Role.STUDENT)
        cls.running = Project.objects.create(student=cls.running_student, title="Running Topic Nobody Should See",
                                             department=department, programme=programme)
        cls.document = ProjectDocument.objects.create(
            archived_project=cls.archived, title="Final report", document_type="report",
            file=SimpleUploadedFile("final.pdf", b"%PDF-1.4"), visibility=ProjectDocument.Visibility.BAZE_USERS,
        )

    def test_a_visitor_browses_and_searches_completed_projects(self):
        page = self.client.get(reverse("repository"), {"q": "warning"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Early Warning System for Student Performance")
        self.assertNotContains(page, "Running Topic Nobody Should See")
        self.assertNotContains(page, f'href="{reverse("running_topics")}"')  # no Running topics tab for visitors
        self.assertContains(page, "shown as summaries")

    def test_a_visitor_sees_the_summary_but_not_files_or_the_student_identification_number(self):
        page = self.client.get(reverse("past_project_detail", args=[self.archived.pk]))
        self.assertEqual(page.status_code, 200)
        for shown in ("Early Warning System for Student Performance", "Validate across the whole university.", "Julius Makinde",
                      "Daniel Akpan"):
            self.assertContains(page, shown)
        self.assertNotContains(page, "BU/21A/CS/4417")
        self.assertNotContains(page, reverse("download_project_document", args=[self.document.pk]))
        self.assertContains(page, "to see the project's files")

    def test_files_running_topics_and_changes_still_need_a_login(self):
        login = reverse("login")
        for url in (reverse("download_project_document", args=[self.document.pk]), reverse("running_topics"),
                    reverse("current_project_detail", args=[self.running.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(login, response["Location"])
        response = self.client.post(reverse("past_project_detail", args=[self.archived.pk]), {"action": "set_semester", "semester": "25B"})
        self.assertEqual(response.status_code, 403)

    def test_contact_details_follow_the_students_own_choice(self):
        page = self.client.get(reverse("past_project_detail", args=[self.archived.pk]))
        self.assertContains(page, "daniel@example.com")  # made public by the student
        self.assertNotContains(page, "+234 800 000 0101")  # signed-in only
        User.objects.filter(pk=self.student.pk).update(personal_email_visibility=ContactVisibility.SIGNED_IN)
        self.assertNotContains(self.client.get(reverse("past_project_detail", args=[self.archived.pk])), "daniel@example.com")
        # Signed-in users see what is public as well.
        User.objects.filter(pk=self.student.pk).update(personal_email_visibility=ContactVisibility.PUBLIC)
        self.client.force_login(self.supervisor)
        page = self.client.get(reverse("past_project_detail", args=[self.archived.pk]))
        self.assertContains(page, "daniel@example.com")
        self.assertContains(page, "+234 800 000 0101")

    def test_a_phone_number_can_never_be_public(self):
        User.objects.filter(pk=self.student.pk).update(phone_visibility=ContactVisibility.PUBLIC)  # even if forced
        self.assertNotContains(self.client.get(reverse("past_project_detail", args=[self.archived.pk])), "+234 800 000 0101")
        form = ContactDetailsForm({"personal_email": "daniel@example.com", "personal_email_visibility": "public",
                                   "phone": "+234 800 000 0101", "phone_visibility": "public"}, instance=self.student)
        self.assertFalse(form.is_valid())
        self.assertIn("phone_visibility", form.errors)
        self.assertNotIn("personal_email_visibility", form.errors)

    def test_sample_records_stay_out_of_the_public_showcase_on_a_real_site(self):
        sample = ArchivedProject.objects.create(title="Sample Project For The Demo", year=2024, department=self.archived.department,
                                                programme=self.archived.programme, student=self.running_student, is_demo=True)
        self.assertNotContains(self.client.get(reverse("repository")), "Sample Project For The Demo")
        self.assertEqual(self.client.get(reverse("past_project_detail", args=[sample.pk])).status_code, 404)

    def test_the_welcome_page_says_completed_projects_are_open(self):
        self.assertContains(self.client.get(reverse("home")), "Anyone can browse completed projects.")

    @override_settings(PUBLIC_REPOSITORY=False)
    def test_switching_the_showcase_off_requires_a_login_again(self):
        for url in (reverse("repository"), reverse("past_project_detail", args=[self.archived.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)
        self.assertContains(self.client.get(reverse("home")), "Log in to open the repository.")
