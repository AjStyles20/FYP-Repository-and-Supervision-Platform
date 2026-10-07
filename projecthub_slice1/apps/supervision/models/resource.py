"""Reading, templates and links a supervisor shares with their students."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q


def validate_resource_size(upload):
    if upload.size > 25 * 1024 * 1024:
        raise ValidationError("Shared files must be 25 MB or smaller.")


def student_resource_scope(student):
    """Resources a student may see: only those sent to one of their current projects (R-25).

    `projects` is how the supervisor's form targets supervisees; the older single `project` field
    is still honoured for rows that use it. Nothing is shared with a whole department.
    """
    return Q(projects__student=student, projects__archived=False) | Q(project__student=student, project__archived=False)


class SharedResource(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shared_resources",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resources",
        help_text="Leave empty to share with the whole department.",
    )
    projects = models.ManyToManyField(
        "projects.Project",
        blank=True,
        related_name="shared_resources",
        help_text="The current supervisees who can access this resource.",
    )
    department = models.ForeignKey(
        "academics.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resources",
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    url = models.URLField(blank=True, help_text="Use this for material that already lives online.")
    file = models.FileField(
        upload_to="shared_resources/%Y/%m/",
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "zip", "txt"]
            ),
            validate_resource_size,
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(url="") | ~Q(file=""),
                name="shared_resource_has_url_or_file",
            )
        ]

    def __str__(self):
        return self.title

    @property
    def audience_label(self):
        if self.project_id:
            return f"For {self.project.student_name}"
        if self.department_id:
            return f"All of {self.department.name}"
        return "Everyone"

    @property
    def link_href(self):
        return self.url or (self.file.url if self.file else "")
