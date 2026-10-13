"""CSV import of historic projects: all or nothing, clear row errors, the supervisor rule, the sample file."""

import csv
import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import DataError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, User
from apps.audit.models import AuditEvent

from .imports import CSV_COLUMNS, import_archived_projects
from .models import ArchivedProject

SAMPLE = settings.BASE_DIR.parent / "docs" / "sample_import.csv"


def csv_file(*rows):
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})
    return SimpleUploadedFile("projects.csv", out.getvalue().encode("utf-8"), content_type="text/csv")


class CsvImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        faculty = Faculty.objects.create(name="Faculty of Computing and Applied Sciences")
        cls.department = Department.objects.create(faculty=faculty, name="Computer Science")
        cls.other = Department.objects.create(faculty=faculty, name="Software Engineering")
        cls.programme = Programme.objects.create(department=cls.department, name="Computer Science", degree_type="BSc")
        cls.student = User.objects.create(username="ada", role=Role.STUDENT)
        StudentProfile.objects.create(user=cls.student, student_number="BU/20/CS/1", programme=cls.programme)
        cls.supervisor = User.objects.create(username="okoro", role=Role.SUPERVISOR, department=cls.department)
        cls.retired = User.objects.create(username="retired", role=Role.SUPERVISOR, department=cls.department, is_active=False)
        cls.outsider = User.objects.create(username="outsider", role=Role.SUPERVISOR, department=cls.other)
        cls.admin = User.objects.create(username="sysadmin", role=Role.ADMIN, department=cls.department)

    def row(self, **changes):
        return {
            "title": "Library Seat Booking", "year": "2024", "completed_on": "2024-07-05",
            "department": "Computer Science", "programme": "Computer Science", "degree_type": "BSc",
            "student_username": "ada", "supervisor_username": "okoro", "previous_supervisors": "",
            **changes,
        }

    def test_a_good_file_imports_every_row(self):
        imported, errors = import_archived_projects(csv_file(self.row(), self.row(title="Second topic", previous_supervisors="retired")))
        self.assertEqual((imported, errors), (2, []))
        self.assertEqual(list(ArchivedProject.objects.get(title="Second topic").previous_supervisors.all()), [self.retired])

    def test_previous_supervisors_are_kept_once_and_never_repeat_the_final_supervisor(self):
        imported, errors = import_archived_projects(csv_file(self.row(previous_supervisors="okoro; retired;retired")))
        self.assertEqual((imported, errors), (1, []))
        self.assertEqual(list(ArchivedProject.objects.get().previous_supervisors.all()), [self.retired])

    def test_one_bad_row_imports_nothing_and_every_bad_row_is_listed(self):
        imported, errors = import_archived_projects(csv_file(
            self.row(),
            self.row(title="Bad year", year="twenty"),
            self.row(title="Unknown student", student_username="nobody"),
            self.row(title="Bad date", completed_on="05/07/2024"),
        ))
        self.assertEqual(imported, 0)
        self.assertEqual([line for line, _ in errors], [3, 4, 5])
        self.assertIn('Year "twenty" must be a whole number', errors[0][1])
        self.assertIn('No student account with username "nobody"', errors[1][1])
        self.assertIn("must be a date such as 2025-06-30", errors[2][1])
        self.assertFalse(ArchivedProject.objects.exists())

    def test_the_same_project_twice_in_one_file_is_caught(self):
        imported, errors = import_archived_projects(csv_file(self.row(), self.row()))
        self.assertEqual((imported, [line for line, _ in errors]), (0, [3]))
        self.assertFalse(ArchivedProject.objects.exists())

    def test_a_database_error_becomes_a_row_error_not_a_traceback(self):
        with mock.patch("apps.projects.imports.ArchivedProject.objects.create", side_effect=DataError("value too long")):
            imported, errors = import_archived_projects(csv_file(self.row()))
        self.assertEqual(imported, 0)
        self.assertEqual(errors[0][0], 2)
        self.assertIn("The database refused this row", errors[0][1])
        self.assertFalse(ArchivedProject.objects.exists())

    def test_an_unexpected_error_becomes_a_row_error_and_is_logged(self):
        with mock.patch("apps.projects.imports.ArchivedProject.objects.create", side_effect=RuntimeError("boom")), \
                self.assertLogs("apps.projects.imports", level="ERROR"):
            imported, errors = import_archived_projects(csv_file(self.row()))
        self.assertEqual((imported, errors[0][0]), (0, 2))
        self.assertIn("This row could not be read", errors[0][1])

    def test_supervisors_must_be_academic_staff_of_the_projects_department(self):
        cases = {
            "supervisor from another department": self.row(supervisor_username="outsider"),
            "previous supervisor from another department": self.row(previous_supervisors="okoro;outsider"),
            "administrator as supervisor": self.row(supervisor_username="sysadmin"),
            "student as previous supervisor": self.row(previous_supervisors="ada"),
        }
        for label, row in cases.items():
            with self.subTest(label):
                imported, errors = import_archived_projects(csv_file(row))
                self.assertEqual(imported, 0)
                self.assertIn("must be a supervisor, coordinator or HOD in Computer Science", errors[0][1])
        # A supervisor who has since left is still a valid historic record.
        self.assertEqual(import_archived_projects(csv_file(self.row(supervisor_username="retired")))[0], 1)

    def test_the_page_says_nothing_was_imported_and_lists_the_rows(self):
        admin = User.objects.create(username="admin.user", role=Role.ADMIN)
        self.client.force_login(admin)
        response = self.client.post(reverse("import_projects"), {"file": csv_file(self.row(), self.row(title="", year="1800"))})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing was imported")
        self.assertContains(response, "Row 3: Title is required.")
        self.assertFalse(ArchivedProject.objects.exists())
        self.assertEqual(AuditEvent.objects.get(action="repository.csv_import").details, {"imported": 0, "rejected_rows": 1})


class SampleImportFileTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp(prefix="projecthub-import-media-")
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

    def test_the_sample_file_imports_after_seed_demo_as_demo_data(self):
        call_command("seed_demo", "--force", stdout=StringIO())
        seeded = list(ArchivedProject.objects.values_list("pk", flat=True))
        with SAMPLE.open("rb") as handle:
            imported, errors = import_archived_projects(SimpleUploadedFile(SAMPLE.name, handle.read()))
        self.assertEqual(errors, [])
        self.assertEqual(imported, 3)
        rows = ArchivedProject.objects.exclude(pk__in=seeded)
        self.assertTrue(all(row.is_demo for row in rows))
        self.assertEqual(
            sorted(rows.get(title="Cafeteria Queue Time Predictor").previous_supervisors.values_list("username", flat=True)),
            ["demo.danjuma", "demo.eze"],
        )
        with self.captureOnCommitCallbacks(execute=True):
            call_command("purge_demo", stdout=StringIO())
        self.assertFalse(ArchivedProject.objects.exists())
