"""Screenshots and demo videos of a project (D-30).

Media hangs off exactly one parent, a running project or an archived one, and moves with the
project when it is archived, like its documents. A video is either an uploaded file or a link to a
video host; an image is always an uploaded file. Files are served only through a permission-checked
view, never as public static files.
"""

from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .archive import ArchivedProject
from .document import ProjectDocument
from .project import Project

IMAGE_EXTENSIONS = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
VIDEO_EXTENSIONS = {"mp4": "video/mp4", "webm": "video/webm"}
MAXIMUM_IMAGE_BYTES = 5 * 1024 * 1024
MAXIMUM_VIDEO_BYTES = 100 * 1024 * 1024
MAXIMUM_IMAGES_PER_PROJECT = 6
MAXIMUM_VIDEOS_PER_PROJECT = 2
VIDEO_LINK_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "drive.google.com", "vimeo.com")


def media_type(name):
    """The served content type for a stored file name, or None if it is not an allowed type."""
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return IMAGE_EXTENSIONS.get(extension) or VIDEO_EXTENSIONS.get(extension)


def _looks_like(head, kind, extension):
    """Check the first bytes, so a renamed file (for example a script called photo.png) is refused."""
    if kind == "image":
        if extension in ("jpg", "jpeg"):
            return head.startswith(b"\xff\xd8\xff")
        if extension == "png":
            return head.startswith(b"\x89PNG\r\n\x1a\n")
        if extension == "webp":
            return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
        return False
    if extension == "mp4":
        return head[4:8] == b"ftyp"
    if extension == "webm":
        return head.startswith(b"\x1a\x45\xdf\xa3")
    return False


def validate_media_upload(upload, kind):
    """Type, size and content checks for an uploaded image or video."""
    extension = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
    allowed = IMAGE_EXTENSIONS if kind == "image" else VIDEO_EXTENSIONS
    if extension not in allowed:
        raise ValidationError(f"Choose a {', '.join(ext.upper() for ext in allowed)} file.")
    limit = MAXIMUM_IMAGE_BYTES if kind == "image" else MAXIMUM_VIDEO_BYTES
    if upload.size > limit:
        raise ValidationError(f"{'Images' if kind == 'image' else 'Videos'} must be {limit // (1024 * 1024)} MB or smaller.")
    position = upload.tell() if hasattr(upload, "tell") else 0
    upload.seek(0)
    head = upload.read(16)
    upload.seek(position)
    if not _looks_like(head, kind, extension):
        raise ValidationError("This file is not a real image or video of the type its name says.")


def validate_video_link(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in VIDEO_LINK_HOSTS:
        raise ValidationError("Use an https link from YouTube, Google Drive or Vimeo.")


class ProjectMedia(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Screenshot or image"
        VIDEO = "video", "Demo video"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name="media")
    archived_project = models.ForeignKey(
        ArchivedProject, on_delete=models.CASCADE, null=True, blank=True, related_name="media"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    caption = models.CharField(max_length=180, help_text="A short description, for example \"Login screen\".")
    file = models.FileField(upload_to="project_media/%Y/%m/", blank=True)
    video_url = models.URLField(blank=True, help_text="A YouTube, Google Drive or Vimeo link, instead of an upload.")
    visibility = models.CharField(
        max_length=12, choices=ProjectDocument.Visibility.choices, default=ProjectDocument.Visibility.BAZE_USERS
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_project_media"
    )
    is_demo = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "uploaded_at"]
        verbose_name_plural = "project media"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(project__isnull=False, archived_project__isnull=True)
                    | Q(project__isnull=True, archived_project__isnull=False)
                ),
                name="project_media_exactly_one_parent",
            ),
            models.CheckConstraint(
                condition=(Q(file="") & ~Q(video_url="") & Q(kind="video")) | (~Q(file="") & Q(video_url="")),
                name="project_media_file_or_video_link",
            ),
        ]

    def __str__(self):
        return self.caption

    @property
    def parent(self):
        return self.project or self.archived_project

    @property
    def content_type(self):
        return media_type(self.file.name) if self.file else ""
