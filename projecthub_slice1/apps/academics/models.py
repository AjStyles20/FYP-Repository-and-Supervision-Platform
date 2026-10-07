"""Faculty → Department → Programme → award.

The whole university is described by this tree. Nothing else in the product branches on a
particular faculty, so adding Law, Medicine or Engineering is a data change, not a code change.
"""

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
