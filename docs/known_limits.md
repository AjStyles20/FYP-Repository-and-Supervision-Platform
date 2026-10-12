# Known limits

These are things the platform does **not** do yet. Each entry says what is missing and what exists instead. Paths are relative to `projecthub_slice1/`.

## Other limits found in the review (docs/review/01-inventory-and-workflows.md)

| Limit | What happens today |
|---|---|
| No "corrections required" loop after a defence (R-11) | Stages only move forward: proposed → … → defended → completed |
| No email verification when a student account is added | The coordinator or administrator adds each student in person, after checking their details; no code is sent to the Baze email (self-registration, which also had no verification, is off) |
| Personal emails and phone numbers are not verified | Each person types their own under My details. The format is checked (a personal email cannot be a Baze address; a phone number must look like one), but no code is sent to confirm it |
| Staff have no page that lists a running project's files | Files can be downloaded by the student and by staff of the project's department, but only the student's "My project" page lists them |
| `SupervisionLogEntry` (running log) has no screens | Meeting records and notices cover progress tracking |
| No pagination on the repository | All matching projects are listed on one page |
| Uploaded videos may not allow skipping ahead | Django serves uploaded videos without range requests, so a browser plays them from the start; some browsers cannot jump to a later point. Production should serve media through the web server (or use a video link) |
| Uploaded videos use server disk space | Up to 2 videos of 100 MB per project. Baze ICT should agree the storage, or students should use a YouTube, Google Drive or Vimeo link |
| A newly allocated student's project shows "Topic to be agreed" | Until the student submits their proposal, the project created at allocation carries that placeholder title, including in Running topics |
| Students cannot request a supervisor change in the app | They ask the coordinator in person (D-27); the coordinator records the reason when making the change |
| The Django admin (`/admin/`) shows every model to superusers | Meeting records are restricted to the people R-33 names in the app itself, but a Django superuser can still view them in the admin (view-only there) |

## Limits of the admin and record protection (docs/explain/admin-integrity.md)

| Limit | What happens today |
|---|---|
| Milestones and project documents can still be changed in the Django admin | They can be added, changed and deleted as inlines on a project and on the *Project documents* admin screen (`ProjectMilestoneInline`, `ProjectDocumentInline`, `ProjectDocumentAdmin` in `apps/projects/admin.py`). Stage, stage dates, archived, supervisor and all workflow records are read-only there |
| Deleting a student outside the admin deletes their projects | `Project.student` is `CASCADE`: from the shell or in code, the student's projects go with every status event, approval, completion, assignment, meeting, milestone and document on them. Only `PROTECT` stops it (`ProtectedError`): when the student is the actor of an audit event or has an archived project. The Django admin refuses the delete once the student has a project; a student without a project can still be deleted there |
| On MySQL without its time zone tables, the admin's meeting list fails | Its `date_hierarchy` makes MySQL use `CONVERT_TZ` (`USE_TZ` on, `TIME_ZONE = "Africa/Lagos"`), and the page fails with "Database returned an invalid datetime value". The meeting change pages and the application's own pages work. Fix: load the server's time zone tables, or remove `date_hierarchy` from `SupervisionMeetingAdmin` |
| The audit triggers can be dropped | Only `audit_auditevent` has triggers. An account with MySQL's TRIGGER privilege can drop them, and the documented setup grants the application account all privileges on its database |
| Review pages do not follow the counter rule yet | On a database holding both demo and real data, a real coordinator's or HOD's counters leave out demo projects, but the Approval register, Student allocation, supervision and convocation pages (`apps/projects/views.py`) still list them. A demo-only or real-only database is unaffected |
