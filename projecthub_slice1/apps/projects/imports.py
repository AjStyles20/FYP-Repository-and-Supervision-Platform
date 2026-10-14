"""Import approved historic project summaries from a CSV file, all or nothing.

Every row is checked inside one transaction, each in its own savepoint so a database error in one
row is reported like any other bad row. If any row is bad, the whole import is rolled back and
every bad row is listed with its CSV line number, so the file can be corrected and uploaded again.
A sample file with demo data is in docs/sample_import.csv (it imports after seed_demo).
"""

import csv
import logging
from datetime import date
from io import StringIO

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction

from apps.accounts.models import Role, User
from apps.academics.models import Department, Programme, Semester

from .models import ArchivedProject
from .services.assignment import can_supervise_in

CSV_COLUMNS = ("title", "description", "keywords", "year", "completed_on", "department", "programme", "degree_type", "student_username", "supervisor_username", "gap_summary", "previous_supervisors")
MAX_ROWS = 1000

logger = logging.getLogger(__name__)


def import_archived_projects(upload):
    """Returns (imported_count, [(csv_line, message), ...]). The count is 0 whenever a row is rejected."""
    try:
        content = upload.read().decode("utf-8-sig")
    except (AttributeError, UnicodeDecodeError) as error:
        raise ValidationError("The file must be a UTF-8 CSV.") from error
    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames or not set(CSV_COLUMNS).issubset({name.strip() for name in reader.fieldnames}):
        raise ValidationError("The CSV is missing one or more required headers.")
    imported, errors = 0, []
    with transaction.atomic():
        for row_number, raw in enumerate(reader, start=2):
            row = {str(key).strip(): (value or "").strip() for key, value in raw.items() if key is not None}
            if not any(row.values()):
                continue
            if row_number > MAX_ROWS + 1:
                errors.append((row_number, f"The file limit is {MAX_ROWS:,} data rows."))
                break
            try:
                with transaction.atomic():
                    _import_row(row)
                imported += 1
            except ValidationError as error:
                errors.append((row_number, " ".join(error.messages)))
            except DatabaseError:
                errors.append((row_number, "The database refused this row. Check for values that are too long."))
            except Exception:  # never show a traceback for one bad row
                logger.exception("CSV import: unexpected error in row %s", row_number)
                errors.append((row_number, "This row could not be read. Check every value in it."))
        if errors:
            transaction.set_rollback(True)
            return 0, errors
    return imported, errors


def _one(queryset, missing, several):
    matches = list(queryset[:2])
    if not matches:
        raise ValidationError(missing)
    if len(matches) > 1:
        raise ValidationError(several)
    return matches[0]


def _supervisor(username, department, label):
    user = _one(User.objects.filter(username=username), f'No account with username "{username}" ({label}).',
                f'More than one account matches "{username}" ({label}).')
    if not can_supervise_in(user, department.pk, require_active=False):
        raise ValidationError(
            f'{label.capitalize()} "{username}" must be a supervisor, coordinator or Head of Department in {department.name}.'
        )
    return user


def _import_row(row):
    title = row["title"]
    if not title:
        raise ValidationError("Title is required.")
    try:
        year = int(row["year"])
    except ValueError:
        raise ValidationError(f'Year "{row["year"]}" must be a whole number such as 2025.') from None
    if year < 1900 or year > date.today().year + 5:
        raise ValidationError(f"Year {year} is outside the supported range (1900 to {date.today().year + 5}).")
    try:
        completed_on = date.fromisoformat(row["completed_on"]) if row["completed_on"] else None
    except ValueError:
        raise ValidationError(f'completed_on "{row["completed_on"]}" must be a date such as 2025-06-30.') from None
    department = _one(Department.objects.filter(name__iexact=row["department"]),
                      f'No department named "{row["department"]}".',
                      f'More than one department is named "{row["department"]}".')
    programme = _one(
        Programme.objects.filter(department=department, name__iexact=row["programme"], degree_type__iexact=row["degree_type"]),
        f'No programme "{row["programme"]} {row["degree_type"]}" in {department.name}.',
        f'More than one programme "{row["programme"]} {row["degree_type"]}" in {department.name}.',
    )
    student = _one(User.objects.filter(username=row["student_username"], role=Role.STUDENT),
                   f'No student account with username "{row["student_username"]}".',
                   f'More than one student matches "{row["student_username"]}".')
    profile = getattr(student, "student_profile", None)
    if profile and profile.programme_id != programme.pk:
        raise ValidationError(f'Student "{student.username}" is registered on a different programme.')
    supervisor = _supervisor(row["supervisor_username"], department, "supervisor") if row["supervisor_username"] else None
    previous = []
    for username in filter(None, (item.strip() for item in row["previous_supervisors"].split(";"))):
        person = _supervisor(username, department, "previous supervisor")
        # Each person once, and never the final supervisor as an earlier one too.
        if person not in previous and person != supervisor:
            previous.append(person)
    semester = None
    code = row.get("semester", "").upper()  # optional column (D-38)
    if code:
        semester = Semester.objects.filter(code=code).first()
        if semester is None:
            raise ValidationError(f'No semester "{code}". Add it under Semesters first, or leave the cell empty.')
    if ArchivedProject.objects.filter(title=title[:255], student=student, year=year).exists():
        raise ValidationError("A past project with this title, student and year already exists.")
    project = ArchivedProject.objects.create(
        title=title[:255], description=row["description"], keywords=row["keywords"][:255],
        year=year, completed_on=completed_on, semester=semester, department=department, programme=programme,
        student=student, supervisor=supervisor, gap_summary=row["gap_summary"],
        is_demo=student.is_demo,  # a row about a demo student is demo data, so purge_demo removes it
    )
    if previous:
        project.previous_supervisors.set(previous)
