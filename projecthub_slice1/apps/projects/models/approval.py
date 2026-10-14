"""The final-year project approval form and the Head of Department completion sign-off.

The department's paper process is: the student agrees a topic with a supervisor, the supervisor
fills in and signs the approval form, and the student takes it to the member of staff who logs
approved projects. This model is that form, plus the completion sign-off the Head of Department records at the
end (D-08, D-15).
"""

from django.conf import settings
from django.db import models

from apps.accounts.models import Role

from .project import Project


class SupervisorDecision(models.TextChoices):
    PENDING = "pending", "Not yet decided"
    ACCEPTED = "accepted", "Accepted as proposed"
    ACCEPTED_WITH_CHANGES = "accepted_with_changes", "Accepted with changes"
    REJECTED = "rejected", "Not accepted"


class ProjectApprovalForm(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="approval_form")
    approval_method = models.CharField(
        max_length=24,
        choices=[
            ("topic_only", "Topic, aim and methodology"),
            ("literature_review", "Literature review and research gap"),
            ("working_project", "Working project demonstration"),
        ],
        default="topic_only",
        help_text="Snapshot of the assigned supervisor's criteria when they decide.",
    )
    approval_criteria_snapshot = models.TextField(
        blank=True,
        default="",
        help_text="Snapshot of the supervisor's additional criteria when the decision was made.",
    )

    # What the student proposes.
    proposed_title = models.CharField(max_length=255)
    problem_statement = models.TextField(blank=True)
    objectives = models.TextField(blank=True)
    methodology = models.TextField(blank=True)
    tools_and_technologies = models.CharField(max_length=255, blank=True)
    literature_review = models.TextField(blank=True)
    research_gap = models.TextField(blank=True)
    working_project_demonstration = models.TextField(blank=True)
    student_name_on_form = models.CharField(max_length=150, blank=True)
    student_signed_on = models.DateField(null=True, blank=True)

    # What the supervisor decides.
    supervisor_decision = models.CharField(
        max_length=30,
        choices=SupervisorDecision.choices,
        default=SupervisorDecision.PENDING,
    )
    supervisor_comments = models.TextField(blank=True)
    supervisor_name_on_form = models.CharField(max_length=150, blank=True)
    supervisor_signed_on = models.DateField(null=True, blank=True)

    # What the department records once the form comes back.
    coordinator_logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logged_approval_forms",
    )
    coordinator_logged_on = models.DateField(null=True, blank=True)
    coordinator_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Final-year project approval form"

    def __str__(self):
        return f"Approval form · {self.project.title}"

    @property
    def is_supervisor_signed(self):
        return bool(self.supervisor_signed_on) and self.supervisor_decision != SupervisorDecision.PENDING

    @property
    def is_logged(self):
        return self.coordinator_logged_on is not None

    @property
    def state_label(self):
        if self.is_logged:
            return "Logged by the department"
        if self.supervisor_decision == SupervisorDecision.REJECTED and self.is_supervisor_signed:
            return "Declined; student may revise and resubmit"
        if self.is_supervisor_signed:
            return "Signed by the supervisor"
        if self.student_signed_on:
            return "With the supervisor"
        return "Draft"


class ApprovalDecisionStep(models.TextChoices):
    SUPERVISOR = "supervisor", "Supervisor decision"
    COORDINATOR_LOG = "coordinator_log", "Logged by the department"


class ApprovalDecisionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Approval decisions are append-only.")

    def delete(self):
        raise PermissionError("Approval decisions are append-only.")


class ProjectApprovalDecision(models.Model):
    """Append-only history of every decision taken on a project's approval form.

    ProjectApprovalForm holds the form as it is now, and is reset when a student revises and
    resubmits. This keeps one row per supervisor decision and per departmental log entry, with a
    copy of what was decided on, so earlier "not accepted" decisions and their comments survive.
    Rows can be added but never changed or deleted by application code.
    """

    objects = ApprovalDecisionQuerySet.as_manager()

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="approval_decisions")
    step = models.CharField(max_length=24, choices=ApprovalDecisionStep.choices)
    # The supervisor's decision; blank for a departmental log entry.
    decision = models.CharField(max_length=30, choices=SupervisorDecision.choices, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_decisions",
    )
    name_on_form = models.CharField(max_length=150, blank=True)
    decided_on = models.DateField(null=True, blank=True, help_text="Date signed or logged, as written on the form.")
    proposed_title = models.CharField(max_length=255)
    approval_method = models.CharField(max_length=24, blank=True)
    approval_criteria_snapshot = models.TextField(blank=True)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.get_step_display()} · {self.project.title}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Approval decisions are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Approval decisions are append-only.")


class ProjectCompletion(models.Model):
    """The Head of Department's completion sign-off. Archiving follows from this, not from the defence."""

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="completion")
    hod = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="signed_completions",
        limit_choices_to={"role": Role.HOD},
    )
    signed_on = models.DateField()
    completion_note = models.TextField(blank=True, help_text="What was checked before signing off.")
    gap_summary = models.TextField(blank=True, help_text="Carried onto the archived record.")
    # Sign-off needs either a gap summary or this explicit confirmation that there is none.
    no_gap_confirmed = models.BooleanField(default=False)

    # Graduation is confirmed here and nowhere else (D-15); it is never inferred.
    graduation_verified = models.BooleanField(default=False)
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)

    archived_project = models.OneToOneField(
        "projects.ArchivedProject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completion_record",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-signed_on"]

    def __str__(self):
        return f"Completion · {self.project.title}"
