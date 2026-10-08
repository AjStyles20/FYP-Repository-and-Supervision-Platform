from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    SUPERVISOR = "supervisor", "Supervisor"
    COORDINATOR = "coordinator", "Coordinator"
    HOD = "hod", "Head of Department"
    ADMIN = "admin", "Administrator"


STAFF_ROLES = (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN)


class ProjectHubUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields["role"] = Role.ADMIN
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    objects = ProjectHubUserManager()

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    department = models.ForeignKey(
        "academics.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )
    can_assign_supervisors = models.BooleanField(
        default=False,
        help_text="Allows this staff member to assign or reassign supervisors for projects in their department.",
    )
    is_demo = models.BooleanField(default=False)
    must_change_password = models.BooleanField(
        default=False,
        help_text="Set when an administrator creates the account with a temporary password; "
                  "the person must choose their own password before using the site.",
    )

    @property
    def has_staff_role(self):
        """True for supervisor, coordinator, HOD and admin roles (not the same as Django's is_staff)."""
        return self.role in STAFF_ROLES

    def __str__(self):
        return self.get_full_name() or self.username


class StudentProfile(models.Model):
    class Status(models.TextChoices):
        CURRENT = "current", "Current"
        FYP_COMPLETED = "fyp_completed", "FYP completed"
        GRADUATED = "graduated", "Graduated"

    class RegistrationStatus(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    student_number = models.CharField(max_length=30, unique=True)  # shown to staff only
    programme = models.ForeignKey("academics.Programme", on_delete=models.PROTECT, related_name="students")
    enrolment_year = models.PositiveSmallIntegerField(null=True, blank=True)
    # Student status is separate from project status: finishing a project is not graduating.
    student_status = models.CharField(max_length=20, choices=Status.choices, default=Status.CURRENT)
    registration_status = models.CharField(
        max_length=10,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.APPROVED,
    )
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_consent = models.BooleanField(default=False, help_text="Contact is shown publicly only if True")

    @property
    def award(self):
        return self.programme.award

    @property
    def has_finished_study(self):
        return self.student_status in (self.Status.FYP_COMPLETED, self.Status.GRADUATED)

    def __str__(self):
        return f"{self.user} ({self.student_number})"


class SupervisorProfile(models.Model):
    """Extra academic detail for a member of staff who supervises.

    This is a public-facing professional profile: the repository shows it so a current student
    can see who a past project was supervised by and what that supervisor works on.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="supervisor_profile")
    class ApprovalMethod(models.TextChoices):
        TOPIC_ONLY = "topic_only", "Topic, aim and methodology"
        LITERATURE_REVIEW = "literature_review", "Literature review and research gap"
        WORKING_PROJECT = "working_project", "Working project demonstration"

    approval_method = models.CharField(
        max_length=24,
        choices=ApprovalMethod.choices,
        default=ApprovalMethod.TOPIC_ONLY,
        help_text="Evidence required before you accept a student's project proposal.",
    )
    approval_criteria = models.TextField(
        blank=True,
        default="",
        help_text="Additional proposal criteria students should meet before requesting your review.",
    )
    title = models.CharField(max_length=30, blank=True)  # Dr., Mrs., Prof.
    office = models.CharField(max_length=80, blank=True, default="")
    specialisation = models.CharField(
        max_length=160, blank=True, default="", help_text="Subject area, e.g. Distributed systems."
    )
    research_interests = models.TextField(
        blank=True, default="", help_text="Free text; shown on the public staff profile."
    )
    is_accepting_students = models.BooleanField(
        default=True,
        help_text="Unchecked means this supervisor is not taking new final-year students this session.",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} {self.user}".strip()
