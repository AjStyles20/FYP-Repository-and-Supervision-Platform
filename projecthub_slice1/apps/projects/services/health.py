"""Project health score: a 0-100 risk number with the reasons behind it.

    risk = w_meeting    * min(days_since_last_meeting / meeting_limit_days, 1)
         + w_milestones * min(overdue_milestones / overdue_milestone_limit, 1)
         + w_stage      * min(days_since_stage_change / expected_days_for_stage, 1)
    score = round(100 * risk)

Higher means more at risk. Bands: below 30 on track, 30 to 60 watch, above 60 at risk. The weights,
limits, bands and expected days per stage live in settings (HEALTH_*). They are heuristics chosen by
hand, not validated against real project outcomes; see docs/explain/health-score.md.

The function only reads. It walks project.meetings, .milestones, .status_events and
.supervisor_assignments with .all(), so a list page can prefetch them and avoid one query per project.
"""

from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone

from ..models import ProjectStage

DEFAULT_WEIGHTS = {"meeting": 0.4, "milestones": 0.3, "stage": 0.3}
DEFAULT_BANDS = {"watch": 30, "at_risk": 60}
DEFAULT_MEETING_LIMIT_DAYS = 14
DEFAULT_OVERDUE_MILESTONE_LIMIT = 3
DEFAULT_EXPECTED_DAYS = {"0": 14, "1": 14, "2": 7, "3": 90, "4": 30, "5": 21}

ON_TRACK, WATCH, AT_RISK = "on_track", "watch", "at_risk"
BAND_LABELS = {ON_TRACK: "On track", WATCH: "Watch", AT_RISK: "At risk"}

HEALTH_PREFETCH = ("meetings", "milestones", "status_events", "supervisor_assignments")


@dataclass(frozen=True)
class Health:
    score: int
    reasons: list = field(default_factory=list)

    @property
    def band(self):
        return health_band(self.score)

    @property
    def band_label(self):
        return BAND_LABELS[self.band]


def _setting(name, default):
    return getattr(settings, name, default)


def health_band(score):
    bands = _setting("HEALTH_BANDS", DEFAULT_BANDS)
    if score > bands["at_risk"]:
        return AT_RISK
    if score >= bands["watch"]:
        return WATCH
    return ON_TRACK


def _days(since, now):
    return max((now - since).days, 0)


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def health_score(project, now=None):
    """Health of an active project, or None for a completed or archived one (nothing left to track)."""
    if project.archived or project.stage == ProjectStage.COMPLETED:
        return None
    from apps.supervision.models import MeetingStatus  # supervision imports projects, not the reverse

    now = now or timezone.now()
    today = timezone.localdate(now)
    weights = _setting("HEALTH_WEIGHTS", DEFAULT_WEIGHTS)
    meeting_limit = _setting("HEALTH_MEETING_LIMIT_DAYS", DEFAULT_MEETING_LIMIT_DAYS)
    milestone_limit = _setting("HEALTH_OVERDUE_MILESTONE_LIMIT", DEFAULT_OVERDUE_MILESTONE_LIMIT)
    expected_days = _setting("HEALTH_EXPECTED_DAYS", DEFAULT_EXPECTED_DAYS)
    reasons = []

    # 1. Time since the last held meeting. With none held yet, count from when the current
    #    supervisor was assigned, or from project creation if nobody is assigned.
    held = [m.scheduled_for for m in project.meetings.all() if m.status == MeetingStatus.HELD and m.scheduled_for <= now]
    if held:
        meeting_days = _days(max(held), now)
        meeting_text = f"Last held meeting {_plural(meeting_days, 'day')} ago"
    else:
        current = [a.assigned_at for a in project.supervisor_assignments.all() if a.ended_at is None]
        if project.supervisor_id and current:
            meeting_days = _days(max(current), now)
            meeting_text = f"No held meeting yet; supervisor assigned {_plural(meeting_days, 'day')} ago"
        else:
            meeting_days = _days(project.created_at, now)
            meeting_text = f"No held meeting yet; project created {_plural(meeting_days, 'day')} ago"
    meeting_points = weights["meeting"] * min(meeting_days / meeting_limit, 1)
    reasons.append(f"{meeting_text} (limit {meeting_limit} days): +{round(100 * meeting_points)}")

    # 2. Overdue milestones: a due date before today and not done.
    milestones = list(project.milestones.all())
    overdue = sum(1 for m in milestones if not m.done and m.due_date is not None and m.due_date < today)
    milestone_points = weights["milestones"] * min(overdue / milestone_limit, 1)
    if not milestones:
        reasons.append("No milestones set: +0")
    else:
        reasons.append(f"{_plural(overdue, 'overdue milestone')} (limit {milestone_limit}): +{round(100 * milestone_points)}")

    # 3. Time at the current stage against the expected time for that stage.
    changes = [event.created_at for event in project.status_events.all()]
    stage_days = _days(max(changes) if changes else project.created_at, now)
    stage_label = project.get_stage_display()
    expected = expected_days.get(project.stage)
    if expected:
        stage_points = weights["stage"] * min(stage_days / expected, 1)
        reasons.append(f"{_plural(stage_days, 'day')} at {stage_label} (expected {expected} days): +{round(100 * stage_points)}")
    else:
        stage_points = 0
        reasons.append(f"{_plural(stage_days, 'day')} at {stage_label} (no expected time set): +0")

    score = round(100 * (meeting_points + milestone_points + stage_points))
    return Health(score=max(0, min(score, 100)), reasons=reasons)


def can_see_health(user, project):
    """Supervisors and coordinators only: the project's supervisor, or a coordinator in its department."""
    from apps.accounts.models import Role

    if project.supervisor_id and project.supervisor_id == user.pk:
        return True
    return user.role == Role.COORDINATOR and bool(user.department_id) and user.department_id == project.department_id
