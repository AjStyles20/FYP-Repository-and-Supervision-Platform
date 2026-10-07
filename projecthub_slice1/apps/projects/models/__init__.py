"""Project models, grouped by concern.

Django treats this package exactly like a single models module, so the app label and every model
name stay the same: `projects.Project`, `projects.ArchivedProject`, and so on.
"""

from .project import (
    ACTIVE_STAGES,
    STAGE_SEQUENCE,
    SUPERVISOR_CHOICES,
    Project,
    ProjectStage,
    ProjectStatusEvent,
)
from .assignment import ProjectSupervisorAssignment
from .milestone import ProjectMilestone
from .archive import ArchivedProject
from .document import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    MAXIMUM_DOCUMENT_BYTES,
    DocumentType,
    ProjectDocument,
    validate_project_document_size,
)
from .approval import (
    ApprovalDecisionStep,
    ProjectApprovalDecision,
    ProjectApprovalForm,
    ProjectCompletion,
    SupervisorDecision,
)

__all__ = [
    "ACTIVE_STAGES",
    "ALLOWED_DOCUMENT_EXTENSIONS",
    "ApprovalDecisionStep",
    "ArchivedProject",
    "DocumentType",
    "MAXIMUM_DOCUMENT_BYTES",
    "Project",
    "ProjectApprovalDecision",
    "ProjectApprovalForm",
    "ProjectCompletion",
    "ProjectDocument",
    "ProjectMilestone",
    "ProjectStage",
    "ProjectStatusEvent",
    "ProjectSupervisorAssignment",
    "STAGE_SEQUENCE",
    "SUPERVISOR_CHOICES",
    "SupervisorDecision",
    "validate_project_document_size",
]
