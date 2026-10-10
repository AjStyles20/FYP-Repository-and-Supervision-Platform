# Known limits

These are things the platform does **not** do yet. Each entry says what is missing and what exists instead. Paths are relative to `projecthub_slice1/`.

## Students cannot request a meeting from a supervisor's availability (R-21, partial)

- **Exists:** supervisors publish weekly availability windows (`/supervision/availability/`) and their current students are notified. The supervisor then schedules each actual meeting (`/supervision/projects/<id>/meetings/`), and the student is notified.
- **Missing:** booking. The `MeetingRequest` model (`apps/supervision/models/meeting.py`) and `MeetingRequestForm` (`apps/supervision/forms.py`) are kept for a later slice, but nothing uses them. There is no URL, page, link or button that reaches them. The old endpoint `/supervision/projects/<id>/request-meeting/` returned 403 for everyone, so it has been removed and now returns 404.
- **Test:** `apps/supervision/tests.py::test_meeting_requests_have_no_entry_point`.

## Other limits found in the review (docs/review/01-inventory-and-workflows.md)

| Limit | What happens today |
|---|---|
| No "corrections required" loop after a defence (R-11) | Stages only move forward: proposed → … → defended → completed |
| No email verification at registration | An administrator approves each student registration by hand before the account can sign in |
| Staff have no page that lists a running project's files | Files can be downloaded by the student and by staff of the project's department, but only the student's "My project" page lists them |
| Milestones can't be created or edited in the app | Milestones are read-only in the app and editable in the Django admin |
| `SupervisionLogEntry` (running log) has no screens | Meeting records and notices cover progress tracking |
| No pagination on the repository | All matching projects are listed on one page |
| The Django admin (`/admin/`) shows every model to superusers | Meeting records are restricted to the people R-33 names in the app itself, but a Django superuser can still view them in the admin (view-only there) |

## Limits of the admin and record protection (docs/explain/admin-integrity.md)

| Limit | What happens today |
|---|---|
| Milestones and project documents can still be changed in the Django admin | They can be added, changed and deleted as inlines on a project and on the *Project documents* admin screen (`ProjectMilestoneInline`, `ProjectDocumentInline`, `ProjectDocumentAdmin` in `apps/projects/admin.py`). Stage, stage dates, archived, supervisor and all workflow records are read-only there |
| Deleting a student outside the admin deletes their projects | `Project.student` is `CASCADE`: from the shell or in code, the student's projects go with every status event, approval, completion, assignment, meeting, milestone and document on them. Only `PROTECT` stops it (`ProtectedError`): when the student is the actor of an audit event or has an archived project. The Django admin refuses the delete once the student has a project; a student without a project can still be deleted there |
| On MySQL without its time zone tables, the admin's meeting list fails | Its `date_hierarchy` makes MySQL use `CONVERT_TZ` (`USE_TZ` on, `TIME_ZONE = "Africa/Lagos"`), and the page fails with "Database returned an invalid datetime value". The meeting change pages and the application's own pages work. Fix: load the server's time zone tables, or remove `date_hierarchy` from `SupervisionMeetingAdmin` |
| The audit triggers can be dropped | Only `audit_auditevent` has triggers. An account with MySQL's TRIGGER privilege can drop them, and the documented setup grants the application account all privileges on its database |
