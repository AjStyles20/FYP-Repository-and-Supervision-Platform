from django.db import models


class Faculty(models.Model):
    name = models.CharField(max_length=150, unique=True)
    is_demo = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "faculties"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Department(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT, related_name="departments")
    name = models.CharField(max_length=150)
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["faculty__name", "name"]
        constraints = [models.UniqueConstraint(fields=["faculty", "name"], name="uq_department_per_faculty")]

    def __str__(self):
        return f"{self.name} ({self.faculty.name})"


class Programme(models.Model):
    """A degree programme inside a department, e.g. Computer Science BSc."""

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programmes")
    name = models.CharField(max_length=150)
    degree_type = models.CharField(max_length=20, help_text="e.g. BSc, MSc, LLB (confirm the real list with Baze)")
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["department__name", "name", "degree_type"]
        constraints = [
            models.UniqueConstraint(fields=["department", "name", "degree_type"], name="uq_programme_per_department")
        ]

    def __str__(self):
        return f"{self.name} {self.degree_type}"
