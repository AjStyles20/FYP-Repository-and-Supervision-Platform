from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent

from .models import Department, Faculty, Programme


class ManageStructureTests(TestCase):
    """Only administrators change the academic structure; nothing in use can be deleted."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create(username="structure.admin", role=Role.ADMIN)
        cls.coordinator = User.objects.create(username="structure.coordinator", role=Role.COORDINATOR)
        cls.faculty = Faculty.objects.create(name="Faculty of Computing and Applied Sciences", code="FCAS")
        cls.department = Department.objects.create(faculty=cls.faculty, name="Computer Science", code="CS")

    def setUp(self):
        self.client.force_login(self.admin)

    def _post(self, **data):
        return self.client.post(reverse("manage_structure"), data)

    def test_only_admins_can_manage(self):
        self.client.force_login(self.coordinator)
        self.assertEqual(self.client.get(reverse("manage_structure")).status_code, 403)
        self.assertEqual(self.client.get(reverse("academic_structure")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("academic_structure")), "Manage structure")

    def test_add_faculty_department_and_programme_in_order(self):
        self._post(action="add_faculty", **{"faculty-name": "Faculty of Law", "faculty-code": "LAW"})
        law = Faculty.objects.get(name="Faculty of Law")
        self._post(action="add_department", **{"department-faculty": law.pk, "department-name": "Public Law", "department-code": "PL"})
        public_law = Department.objects.get(name="Public Law")
        response = self._post(action="add_programme", **{
            "programme-department": public_law.pk, "programme-name": "Law", "programme-degree_type": "LLB",
            "programme-level": "undergraduate", "programme-duration_years": 5,
        })

        self.assertRedirects(response, reverse("manage_structure"))
        programme = Programme.objects.get(department=public_law)
        self.assertEqual((str(programme), programme.is_demo), ("Law LLB", False))
        self.assertEqual(
            list(AuditEvent.objects.order_by("pk").values_list("action", flat=True)),
            ["structure.faculty_created", "structure.department_created", "structure.programme_created"],
        )

    def test_duplicates_are_rejected(self):
        response = self._post(action="add_department", **{
            "department-faculty": self.faculty.pk, "department-name": "Computer Science", "department-code": "CS2",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["forms"]["department"].errors)
        self.assertEqual(Department.objects.filter(name="Computer Science").count(), 1)

    def test_edit_is_audited_field_by_field(self):
        self.client.post(reverse("edit_structure_item", args=["department", self.department.pk]), {
            "faculty": self.faculty.pk, "name": "Computer Science", "code": "CSC",
        })
        self.department.refresh_from_db()
        self.assertEqual(self.department.code, "CSC")
        self.assertEqual(AuditEvent.objects.get(action="structure.department_updated").details, {"code": {"from": "CS", "to": "CSC"}})

    def test_nothing_in_use_can_be_deleted(self):
        programme = Programme.objects.create(department=self.department, name="Computer Science", degree_type="BSc")
        student = User.objects.create(username="structure.student", role=Role.STUDENT, department=self.department)
        StudentProfile.objects.create(user=student, student_number="BU/26/ST/1", programme=programme)

        for kind, item in (("faculty", self.faculty), ("department", self.department), ("programme", programme)):
            response = self.client.post(reverse("manage_structure"), {"action": "delete", "kind": kind, "pk": item.pk}, follow=True)
            self.assertContains(response, f"Cannot delete {kind}")
        self.assertTrue(Programme.objects.filter(pk=programme.pk).exists())
        self.assertTrue(Department.objects.filter(pk=self.department.pk).exists())
        student.refresh_from_db()
        self.assertEqual(student.department, self.department)

    def test_unused_items_can_be_deleted(self):
        empty = Department.objects.create(faculty=self.faculty, name="Unused Department")

        self._post(action="delete", kind="department", pk=empty.pk)

        self.assertFalse(Department.objects.filter(pk=empty.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(action="structure.department_deleted").exists())

    def test_unknown_kind_is_404(self):
        self.assertEqual(self.client.get(reverse("edit_structure_item", args=["campus", 1])).status_code, 404)
        self.assertEqual(self._post(action="delete", kind="campus", pk=1).status_code, 404)
