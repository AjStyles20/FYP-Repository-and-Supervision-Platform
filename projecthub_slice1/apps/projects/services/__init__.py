"""Project services: the operations that change a project, grouped by concern.

Views call these rather than writing to the models directly, so every rule (audit trail, who may
do what, what happens to the files) lives in one place.
"""

from .approval import log_approved_form, record_supervisor_decision, submit_proposal
from .milestones import apply_faculty_deadlines, create_deadline, remove_deadline, update_deadline
from .assignment import allocate_student, assign_project_supervisor, previous_supervisors_for, supervision_history_for, unassign_project_supervisor
from .counters import staff_with_counters, supervisor_summary
from .lifecycle import record_transition, sign_off_completion
from .repository import (
    SECTION_ALL,
    SECTION_CURRENT,
    SECTION_PAST,
    SECTIONS,
    available_years,
    clean_section,
    current_projects,
    faculties_with_structure,
    local_year,
    past_projects,
    read_filters,
)

__all__ = [
    "SECTION_ALL",
    "SECTION_CURRENT",
    "SECTION_PAST",
    "SECTIONS",
    "assign_project_supervisor",
    "available_years",
    "clean_section",
    "current_projects",
    "faculties_with_structure",
    "local_year",
    "log_approved_form",
    "past_projects",
    "previous_supervisors_for",
    "read_filters",
    "record_supervisor_decision",
    "record_transition",
    "sign_off_completion",
    "staff_with_counters",
    "submit_proposal",
    "supervision_history_for",
    "supervisor_summary",
    "unassign_project_supervisor",
]
