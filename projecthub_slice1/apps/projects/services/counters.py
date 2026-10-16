"""Supervisor counters: how many students, how many approved, how many defended, how many past.

These numbers are what the department's allocation workspace is for. They are aggregate counts
only — no meeting notes or private records are ever exposed through them.
"""

from django.db.models import Count, Q

from apps.accounts.models import Role, User

from ..models import ProjectStage

STAFF_ROLE_VALUES = (Role.SUPERVISOR, Role.COORDINATOR, Role.HOD)


def _active_scope():
    return Q(supervised_projects__archived=False)


def staff_with_counters(queryset=None, department=None, departments=None, viewer=None):
    """Annotate academic staff with their supervision counters.

    `distinct=True` on every count matters: combining several annotations in one query multiplies
    the joined rows otherwise, and the numbers would be wrong. Given a `viewer`, the demo rule of the
    portal counters applies: a real account counts real staff and real projects only.
    """
    queryset = queryset if queryset is not None else User.objects.filter(
        role__in=STAFF_ROLE_VALUES, is_active=True
    )
    if department is not None:
        queryset = queryset.filter(department=department)
    if departments is not None:
        queryset = queryset.filter(department__in=departments)

    active = _active_scope()
    past = Q()
    earlier_past = Q()
    if viewer is not None and not viewer.is_demo:
        queryset = queryset.filter(is_demo=False)
        active &= Q(supervised_projects__is_demo=False)
        past = Q(archived_supervisions__is_demo=False)
        earlier_past = Q(previous_archived_supervisions__is_demo=False)
    return queryset.annotate(
        active_count=Count("supervised_projects", filter=active, distinct=True),
        approved_count=Count(
            "supervised_projects",
            filter=active & Q(supervised_projects__stage__gte=ProjectStage.APPROVED),
            distinct=True,
        ),
        defended_count=Count(
            "supervised_projects",
            filter=active & Q(supervised_projects__stage__gte=ProjectStage.DEFENDED),
            distinct=True,
        ),
        past_count=Count("archived_supervisions", filter=past, distinct=True),
        earlier_past_count=Count("previous_archived_supervisions", filter=earlier_past, distinct=True),
    ).order_by("last_name", "first_name", "username")


def supervisor_summary(user):
    """The counters for one staff member, ready for a profile or workspace header."""
    counted = staff_with_counters(User.objects.filter(pk=user.pk)).first()
    if counted is None:
        return {
            "active_count": 0,
            "approved_count": 0,
            "defended_count": 0,
            "past_count": 0,
            "earlier_past_count": 0,
        }
    return {
        "active_count": counted.active_count,
        "approved_count": counted.approved_count,
        "defended_count": counted.defended_count,
        "past_count": counted.past_count,
        "earlier_past_count": counted.earlier_past_count,
    }
