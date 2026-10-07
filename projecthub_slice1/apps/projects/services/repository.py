"""Search helpers for running topics and the completed project repository."""

from django.db.models import Q

from apps.academics.models import Faculty, QualificationLevel

from ..models import ArchivedProject, Project

SECTION_CURRENT = "current"
SECTION_PAST = "past"
SECTION_ALL = "all"
SECTIONS = (SECTION_CURRENT, SECTION_PAST, SECTION_ALL)

SEARCH_FIELDS = (
    "title",
    "description",
    "keywords",
    "student__first_name",
    "student__last_name",
    "supervisor__first_name",
    "supervisor__last_name",
    "department__name",
    "department__faculty__name",
    "programme__name",
    "programme__degree_type",
)
PAST_SEARCH_FIELDS = SEARCH_FIELDS + ("gap_summary",)

CURRENT_SELECT_RELATED = ("student", "student__student_profile", "department__faculty", "programme", "supervisor")


def read_filters(params):
    """Read the filter set from a query dict, discarding anything that is not a real id."""

    def as_id(name):
        value = (params.get(name) or "").strip()
        return value if value.isdigit() else ""

    level = (params.get("level") or "").strip()
    year = (params.get("year") or "").strip()
    return {
        "q": (params.get("q") or "").strip(),
        "faculty": as_id("faculty"),
        "department": as_id("department"),
        "programme": as_id("programme"),
        "level": level if level in QualificationLevel.values else "",
        "year": year if len(year) == 4 and year.isdigit() else "",
    }


def clean_section(value):
    return value if value in SECTIONS else SECTION_CURRENT


def current_projects(filters, can_see_student_id=False):
    queryset = Project.objects.filter(archived=False).select_related(*CURRENT_SELECT_RELATED)
    queryset = _apply_academic_filters(queryset, filters)
    if filters["year"]:
        queryset = queryset.filter(updated_at__year=int(filters["year"]))
    queryset = _apply_search(queryset, filters["q"], SEARCH_FIELDS, can_see_student_id)
    return queryset.order_by("-updated_at")


def past_projects(filters, can_see_student_id=False):
    queryset = (
        ArchivedProject.objects.filter(
            student__student_profile__student_status="graduated"
        ).select_related(*CURRENT_SELECT_RELATED).prefetch_related("previous_supervisors")
    )
    queryset = _apply_academic_filters(queryset, filters)
    if filters["year"]:
        queryset = queryset.filter(year=int(filters["year"]))
    queryset = _apply_search(queryset, filters["q"], PAST_SEARCH_FIELDS, can_see_student_id)
    return queryset.order_by("-year", "-completed_on", "-created_at")


def available_years():
    current_years = {
        date.year for date in Project.objects.filter(archived=False).dates("updated_at", "year", order="DESC")
    }
    past_years = set(ArchivedProject.objects.filter(
        student__student_profile__student_status="graduated"
    ).values_list("year", flat=True))
    return sorted(current_years | past_years, reverse=True)


def faculties_with_structure():
    """The faculty → department → programme tree used by the browse page and the filters."""
    return Faculty.objects.prefetch_related("departments__programmes").order_by("name")


def _apply_academic_filters(queryset, filters):
    if filters["faculty"]:
        queryset = queryset.filter(department__faculty_id=filters["faculty"])
    if filters["department"]:
        queryset = queryset.filter(department_id=filters["department"])
    if filters["programme"]:
        queryset = queryset.filter(programme_id=filters["programme"])
    if filters["level"]:
        queryset = queryset.filter(programme__level=filters["level"])
    return queryset


def _apply_search(queryset, query, fields, can_see_student_id):
    if not query:
        return queryset
    match = Q()
    for field in fields:
        match |= Q(**{f"{field}__icontains": query})
    if can_see_student_id:
        # Student IDs stay staff-only: a student searching their own ID finds nothing.
        match |= Q(student__student_profile__student_number__icontains=query)
    return queryset.filter(match).distinct()
