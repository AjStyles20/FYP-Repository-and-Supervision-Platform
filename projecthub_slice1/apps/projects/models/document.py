"""Files attached to a current project or to an archived (past) project.

A document hangs off exactly one parent. Visibility controls who may download it: every signed-in
Baze user, or academic staff only. Files are always served through a permission-checked view;
the media directory is never exposed as public static files.
"""

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q

from .archive import ArchivedProject
from .project import Project

MAXIMUM_DOCUMENT_BYTES = 25 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "zip"]


def validate_project_document_size(upload):
    if upload.size > MAXIMUM_DOCUMENT_BYTES:
        raise ValidationError("Project files must be 25 MB or smaller.")


class DocumentType(models.TextChoices):
    PROPOSAL = "proposal", "Proposal"
    REPORT = "report", "Final report"
    PRESENTATION = "presentation", "Presentation"
    POSTER = "poster", "Poster"
    DATA = "data", "Data or code"
    OTHER = "other", "Other"


class ProjectDocument(models.Model):
    class Visibility(models.TextChoices):
        BAZE_USERS = "baze_users", "All signed-in Baze users"
        STAFF_ONLY = "staff_only", "Academic staff only"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name="documents")
    archived_project = models.ForeignKey(
        ArchivedProject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
    )
    title = models.CharField(max_length=180)
    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        default=DocumentType.OTHER,
    )
    file = models.FileField(
        upload_to="project_documents/%Y/%m/",
        validators=[
            FileExtensionValidator(allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS),
            validate_project_document_size,
        ],
    )
    visibility = models.CharField(
        max_length=12,
        choices=Visibility.choices,
        default=Visibility.BAZE_USERS,
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_project_documents",
    )
    is_demo = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(project__isnull=False, archived_project__isnull=True)
                    | Q(project__isnull=True, archived_project__isnull=False)
                ),
                name="project_document_exactly_one_parent",
            )
        ]

    def __str__(self):
        return self.title

    @property
    def filename(self):
        return Path(self.file.name).name

    @property
    def parent_project(self):
        return self.project or self.archived_project
