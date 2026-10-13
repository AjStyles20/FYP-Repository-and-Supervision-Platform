from django.contrib import messages
from django.db.models import Count, ProtectedError, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.audit.services import log_event

from .forms import FORMS, MODELS, SemesterForm
from .models import Faculty, Semester


@role_required(Role.SUPERVISOR, Role.COORDINATOR, Role.HOD, Role.ADMIN)
def structure(request):
    """Read-only view of Faculty > Department > Programme. Staff roles only."""
    faculties = Faculty.objects.prefetch_related("departments__programmes").all()
    return render(request, "academics/structure.html", {"faculties": faculties})


def _kind(kind):
    if kind not in FORMS:
        raise Http404
    return kind


def _delete_blocker(kind, item):
    """Why this item cannot be deleted, or "" if it can. The database protects most links; a
    department's staff and students would only be detached (SET_NULL), so that is checked here."""
    if kind == "department" and item.users.exists():
        count = item.users.count()
        return (f"{count} account{'' if count == 1 else 's'} still belong{'s' if count == 1 else ''} to it. "
                "Move them to another department first.")
    return ""


@role_required(Role.ADMIN)
def manage_structure(request):
    """Add and delete faculties, departments and programmes. Every change is audited."""
    forms = {kind: form_class(prefix=kind) for kind, form_class in FORMS.items()}
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action.startswith("add_"):
            kind = _kind(action.removeprefix("add_"))
            forms[kind] = FORMS[kind](request.POST, prefix=kind)
            if forms[kind].is_valid():
                item = forms[kind].save()
                log_event(actor=request.user, action=f"structure.{kind}_created", summary=f"Added {kind} {item}", obj=item)
                messages.success(request, f"Added {kind} “{item}”.")
                return redirect("manage_structure")
        elif action == "delete":
            kind = _kind(request.POST.get("kind", ""))
            item = get_object_or_404(MODELS[kind], pk=request.POST.get("pk"))
            label = str(item)
            blocker = _delete_blocker(kind, item)
            if not blocker:
                try:
                    item.delete()
                except ProtectedError as error:
                    count = len(error.protected_objects)
                    blocker = (f"{count} linked record{'' if count == 1 else 's'} still use{'s' if count == 1 else ''} it "
                               "(departments, programmes, students or projects).")
            if blocker:
                messages.error(request, f"Cannot delete {kind} “{label}”: {blocker}")
            else:
                log_event(actor=request.user, action=f"structure.{kind}_deleted", summary=f"Deleted {kind} {label}")
                messages.success(request, f"Deleted {kind} “{label}”.")
            return redirect("manage_structure")
        else:
            raise Http404
    faculties = Faculty.objects.prefetch_related("departments__programmes").all()
    return render(request, "academics/manage.html", {"faculties": faculties, "forms": forms})


@role_required(Role.ADMIN)
def edit_structure_item(request, kind, pk):
    """Rename or move one faculty, department or programme."""
    kind = _kind(kind)
    item = get_object_or_404(MODELS[kind], pk=pk)
    form = FORMS[kind](request.POST or None, instance=item)
    before = {name: str(getattr(item, name) or "") for name in form.fields}
    if request.method == "POST" and form.is_valid():
        item = form.save()
        changes = {name: {"from": before[name], "to": str(getattr(item, name) or "")}
                   for name in form.fields if before[name] != str(getattr(item, name) or "")}
        if changes:
            log_event(actor=request.user, action=f"structure.{kind}_updated", summary=f"Updated {kind} {item}", obj=item, details=changes)
        messages.success(request, f"Saved {kind} “{item}”." if changes else "Nothing changed.")
        return redirect("manage_structure")
    return render(request, "academics/edit.html", {"form": form, "kind": kind, "item": item})


@role_required(Role.COORDINATOR, Role.ADMIN)
def semesters(request):
    """Semester labels such as 26A, created by hand (D-38).

    Timing varies, so the coordinator (or the administrator) adds each semester when it is needed;
    its dates are optional notes. Semesters are not deleted here: projects and past records keep them.
    """
    form = SemesterForm(prefix="new")
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "add":
            form = SemesterForm(request.POST, prefix="new")
            if form.is_valid():
                semester = form.save()
                log_event(actor=request.user, action="semester.created", summary=f"Added semester {semester}", obj=semester)
                messages.success(request, f"Added semester {semester}.")
                return redirect("semesters")
        elif action == "update":
            semester = get_object_or_404(Semester, pk=request.POST.get("semester_id"))
            before = {name: str(getattr(semester, name) or "") for name in SemesterForm.Meta.fields}
            edit_form = SemesterForm(request.POST, instance=semester, prefix=f"s{semester.pk}")
            if edit_form.is_valid():
                semester = edit_form.save()
                changes = {name: {"from": before[name], "to": str(getattr(semester, name) or "")}
                           for name in before if before[name] != str(getattr(semester, name) or "")}
                if changes:
                    log_event(actor=request.user, action="semester.updated", summary=f"Updated semester {semester}",
                              obj=semester, details=changes)
                messages.success(request, f"Saved semester {semester}." if changes else "Nothing changed.")
            else:
                errors = " ".join(error for field_errors in edit_form.errors.values() for error in field_errors)
                messages.error(request, f"Semester not saved: {errors}")
            return redirect("semesters")
        else:
            raise Http404
    semesters = Semester.objects.annotate(
        running_count=Count("projects", filter=Q(projects__archived=False), distinct=True),
        archived_count=Count("archived_projects", distinct=True),
        deadline_count=Count("deadlines", distinct=True),
    )
    rows = [{"semester": semester, "form": SemesterForm(instance=semester, prefix=f"s{semester.pk}")} for semester in semesters]
    return render(request, "academics/semesters.html", {"rows": rows, "form": form})
