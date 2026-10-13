"""Faculty → Department → Programme → award.

The whole university is described by this tree. Nothing else in the product branches on a
particular faculty, so adding Law, Medicine or Engineering is a data change, not a code change.
"""

import re

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


class QualificationLevel(models.TextChoices):
    UNDERGRADUATE = "undergraduate", "Undergraduate"
    POSTGRADUATE = "postgraduate", "Postgraduate"


class Faculty(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=12, blank=True, default="", help_text="Code shown in dense lists, e.g. FOC.")
    is_demo = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "faculties"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Department(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT, related_name="departments")
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=12, blank=True, default="", help_text="Short code, e.g. CS.")
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["faculty__name", "name"]
        constraints = [models.UniqueConstraint(fields=["faculty", "name"], name="uq_department_per_faculty")]

    def __str__(self):
        return f"{self.name} ({self.faculty.name})"

    @property
    def head_of_department(self):
        """The HOD is a role on a user in this department; it is not a stored pointer."""
        return (
            self.users.filter(role="hod", is_active=True)
            .order_by("last_name", "first_name")
            .first()
        )

    @property
    def programme_count(self):
        return self.programmes.count()


class Programme(models.Model):
    """A degree programme inside a department, e.g. Computer Science BSc.

    `level` separates undergraduate projects (BSc/BA) from postgraduate dissertations
    (MSc/MA/PhD) so the repository can be browsed by award, as the department asked.
    """

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programmes")
    name = models.CharField(max_length=150)
    degree_type = models.CharField(max_length=20, help_text="Award abbreviation, e.g. BSc, BA, MSc, LLB.")
    level = models.CharField(
        max_length=20,
        choices=QualificationLevel.choices,
        default=QualificationLevel.UNDERGRADUATE,
    )
    duration_years = models.PositiveSmallIntegerField(null=True, blank=True)
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["department__name", "name", "degree_type"]
        constraints = [
            models.UniqueConstraint(fields=["department", "name", "degree_type"], name="uq_programme_per_department")
        ]

    def __str__(self):
        return f"{self.name} {self.degree_type}"

    @property
    def award(self):
        return f"{self.name} {self.degree_type}"

    @property
    def is_postgraduate(self):
        return self.level == QualificationLevel.POSTGRADUATE


semester_code_validator = RegexValidator(
    r"^\d{2}[A-C]$", "Use two digits for the year and A, B or C for the semester, like 26A.", flags=re.IGNORECASE
)


class Semester(models.Model):
    """A semester label such as 26A, entered by hand (D-38).

    Timing varies, so nothing is worked out from dates: the coordinator creates the label, may note
    its start and end for information, and picks it for each project. A project's faculty deadlines
    follow its semester, and the archive keeps the label.
    """

    code = models.CharField(
        max_length=3, unique=True, validators=[semester_code_validator],
        help_text="Two digits for the year and A, B or C, like 26A.",
    )
    starts_on = models.DateField(null=True, blank=True, help_text="Optional, for information only.")
    ends_on = models.DateField(null=True, blank=True, help_text="Optional, for information only.")
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-code"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()  # 26a and 26A are the same semester
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError({"ends_on": "The end date cannot be before the start date."})
