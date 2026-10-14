# Admin integrity

The Django admin (`/admin/`) cannot be used to skip the project workflow. A project's stage, its stage dates and its archived flag change only on the workflow pages, and the records the workflow writes can be viewed in the admin but not added, changed or deleted. Everything an administrator needs day to day is on one page, **Admin tools**.

Code: `ReadOnlyAdmin` and `ProjectAdmin` in `projecthub_slice1/apps/projects/admin.py`. Tests: `AdminCannotBypassWorkflowTests` in `projecthub_slice1/apps/projects/tests_admin.py`, and the admin-hub tests in `LoginAndRolesTests` in `projecthub_slice1/apps/accounts/tests.py`.

## Purpose

Every step of a project, from approval to Head of Department sign-off, is recorded when it happens: a status event, the date of the step, and an audit entry naming who did it. If a superuser could change the stage or a date in the Django admin, the project would show a step that nobody took, with no event and no audit entry behind it. The project history would then be unreliable, and that history is the evidence the platform exists to keep.

## Files involved

Paths are relative to `projecthub_slice1/`.

| File | Role in the feature |
|---|---|
| `apps/projects/admin.py` | `ReadOnlyAdmin` refuses add, change and delete. Status events, supervisor assignments, approval decisions, approval forms and completions use it. `ProjectAdmin` lists `supervisor`, `stage`, `approval_date`, `submission_date`, `defence_date` and `archived` in `readonly_fields`, and refuses delete |
| `apps/supervision/admin.py` | `SupervisionMeetingAdmin` uses `ReadOnlyAdmin`, so meeting records and their version rows (the inline) are view-only |
| `apps/audit/admin.py` | `AuditEventAdmin` is view-only in the same way (unchanged) |
| `apps/projects/models/project.py`, `apps/projects/models/approval.py`, `apps/audit/models.py` | Model guards: status events, approval decisions and audit events refuse update and delete even outside the admin (unchanged) |
| `apps/audit/migrations/0003_append_only_triggers.py` | Database triggers on `audit_auditevent` refuse UPDATE and DELETE (unchanged) |
| `templates/admin_tools.html` | The admin hub: one list of tools (staff accounts, academic structure, CSV import, audit log, Django administration), then registrations and staff accounts |
| `templates/base.html`, `templates/portals/admin.html` | The administrator's menu and portal link to the hub instead of repeating the audit-log and CSV links |
| `apps/projects/tests_admin.py`, `apps/supervision/tests_admin.py`, `apps/accounts/tests.py` | Prove the rules below |

## Flow

1. A superuser opens a project in the Django admin. Stage, the three stage dates and archived are shown as plain text, not as inputs.
2. They change the title and save. Django builds the form only from the editable fields, so a stage, a date or `archived=on` added to the POST by hand is ignored. The title is saved; the protected fields keep their values.
3. They open an approval form or a completion record. The page shows the record but has no Save or Delete button, because `has_change_permission` and `has_delete_permission` return `False`.
4. A POST sent by hand to that record's change, add or delete web address gets **403 Forbidden**. The "Delete selected" bulk action is not offered, because Django removes it when delete permission is `False`.
5. To move a project on, the right person uses the workflow page (`/projects/workflow/<id>/`). That writes the status event, the date and the audit entry together.
6. Day-to-day administration starts at **Admin tools** (`/admin-tools/`), the only page that links to the audit log and the CSV import. Both are refused (403) for every role except administrator.

## Rules

- **The workflow is the only way to change stage, stage dates or archived.** The admin shows them read-only on both the add and the change page; a new project added in the admin starts at **Proposed**.
- **Projects cannot be deleted in the admin**, one at a time or in bulk, because their workflow records would go with them. `purge_demo` still removes demo projects through the ORM.
- **Workflow records are view-only in the admin.** No add, change or delete for status events, supervisor assignments, approval decisions, approval forms, completions, meeting records with their versions, and audit events.
- **Defence in depth for the history tables.** Status events, approval decisions and audit events also refuse update and delete in the model, and audit events are protected by database triggers as well.
- **One admin hub.** The audit log and CSV import are linked only from Admin tools; the menu and the admin portal link to the hub.
- **Logs stay admin-only.** `audit_log` and `import_projects` use `role_required(Role.ADMIN)`.
- **The CSV import cannot leave half a file behind.** `import_archived_projects` (`apps/projects/imports.py`) checks every row in one transaction; if any row is bad, nothing is saved and every bad row is listed with its line number. Supervisors and previous supervisors must pass `can_supervise_in`, the rule `assign_project_supervisor` uses (without the active check, for historic records). A sample with demo data is `docs/sample_import.csv`.
- **Known gaps:**
  - Milestones and project documents can still be added, changed and deleted in the admin.
  - A student account without a project can be deleted in the admin. Once the student has a project, the admin refuses, because the delete would take records it may not delete.
  - On MySQL without time zone tables, the admin's meeting list fails because of its `date_hierarchy`. The meeting change pages work.
  - Outside the admin (shell or code), deleting a student cascades to their projects and every workflow record on them (`Project.student` is `CASCADE`). Only `PROTECT` stops it: when the student is the actor of an audit event, or has an archived project.

## Self-test

1. Why is it not enough to hide the stage field in the workflow pages, and why does the admin need its own rule?
2. A superuser edits the HTML form and adds `stage=completed` to the POST before saving a project in the admin. What happens to the stage, and what happens to the title they also changed?
3. What does Django return for a POST to an approval form's delete web address, and why is the "Delete selected" action missing from the list page?
4. Which of the history tables are protected by something other than the admin, and by what?
5. Which page links to the audit log, and what does a coordinator see if they type the audit log's address?

<details>
<summary>Answers</summary>

1. The Django admin is a separate set of pages with its own forms. Without a rule there, a superuser could change the stage directly and skip the status event, the step date and the audit entry. `ProjectAdmin.readonly_fields` closes that path.
2. The stage is unchanged: read-only fields are left out of the admin form, so the extra POST value is ignored. The title is saved, because it is still editable. `test_project_change_saves_other_fields_but_not_stage_dates_or_archived` checks both.
3. 403 Forbidden, because `ReadOnlyAdmin.has_delete_permission` returns `False`. Django removes the `delete_selected` action for the same reason, so the bulk-delete route deletes nothing either.
4. Status events, approval decisions and audit events: their models and querysets raise `PermissionError` on update or delete. Audit events also have database triggers on `audit_auditevent` (`0003_append_only_triggers.py`).
5. Only Admin tools (`/admin-tools/`). The coordinator gets 403, because `audit_log` is limited to the administrator role.

</details>
