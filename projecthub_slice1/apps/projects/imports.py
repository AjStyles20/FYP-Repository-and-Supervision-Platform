import csv
from datetime import date
from io import StringIO

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import Role, STAFF_ROLES, User
from apps.academics.models import Department, Programme

from .models import ArchivedProject

CSV_COLUMNS = ("title", "description", "keywords", "year", "completed_on", "department", "programme", "degree_type", "student_username", "supervisor_username", "gap_summary", "previous_supervisors")


def import_archived_projects(upload):
    """Import approved historic project summaries. Returns (count, [(row, message), ...])."""
    try:
        content = upload.read().decode("utf-8-sig")
    except (AttributeError, UnicodeDecodeError) as error:
        raise ValidationError("The file must be a UTF-8 CSV.") from error
    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames or not set(CSV_COLUMNS).issubset({name.strip() for name in reader.fieldnames}):
        raise ValidationError("The CSV is missing one or more required headers.")
    imported, errors = 0, []
    for row_number, raw in enumerate(reader, start=2):
        row = {str(key).strip(): (value or "").strip() for key, value in raw.items() if key is not None}
        if not any(row.values()):
            continue
        if row_number > 1002:
            errors.append((row_number, "File limit is 1,000 data rows."))
            break
        try:
            with transaction.atomic():
                title = row["title"]
                if not title:
                    raise ValidationError("Title is required.")
                year = int(row["year"])
                if year < 1900 or year > date.today().year + 5:
                    raise ValidationError("Year is outside the supported range.")
                department = Department.objects.get(name__iexact=row["department"])
                programme = Programme.objects.get(department=department, name__iexact=row["programme"], degree_type__iexact=row["degree_type"])
                student = User.objects.get(username=row["student_username"], role=Role.STUDENT)
                profile = getattr(student, "student_profile", None)
                if profile and profile.programme_id != programme.pk:
                    raise ValidationError("The student's registered programme does not match this row.")
                supervisor = None
                if row["supervisor_username"]:
                    supervisor = User.objects.get(username=row["supervisor_username"], role__in=STAFF_ROLES)
                    if supervisor.department_id != department.pk:
                        raise ValidationError("The supervisor must belong to the project's department.")
                completed_on = date.fromisoformat(row["completed_on"]) if row["completed_on"] else None
                if ArchivedProject.objects.filter(title=title, student=student, year=year).exists():
                    raise ValidationError("A past project with this title, student and year already exists.")
                project = ArchivedProject.objects.create(
                    title=title[:255], description=row["description"], keywords=row["keywords"][:255],
                    year=year, completed_on=completed_on, department=department, programme=programme,
                    student=student, supervisor=supervisor, gap_summary=row["gap_summary"], is_demo=False,
                )
                previous = []
                for username in filter(None, (item.strip() for item in row["previous_supervisors"].split(";"))):
                    previous.append(User.objects.get(username=username, role__in=STAFF_ROLES))
                if previous:
                    project.previous_supervisors.set(previous)
            imported += 1
        except (ValueError, Department.DoesNotExist, Department.MultipleObjectsReturned,
                Programme.DoesNotExist, Programme.MultipleObjectsReturned, User.DoesNotExist,
                User.MultipleObjectsReturned, ValidationError) as error:
            errors.append((row_number, str(error) or "Invalid row data."))
    return imported, errors
