# Progress

**Last updated:** 2026-10-13 · **Core workflows implemented; open questions and known limits remain**

## Implemented

### Accounts and access
- Django 5.2 project, settings read from environment or `.env`
- MySQL connection (utf8mb4); SQLite for the tests, the demo and a quick tryout
- Custom user model with roles: student, supervisor, coordinator, HOD, admin
- Student and supervisor profiles (student number, programme, student status)
- Student accounts are added by the administrator or the department's coordinator (D-28), with Baze email and a full student ID in the Baze format (`BU/23B/IT/7892`: year, batch A-C, department code, number; `STUDENT_ID_REGEX`); active at once with a temporary password. Self-registration with administrator approval exists but is switched off (`STUDENT_SELF_REGISTRATION`)
- Decision email to the student on approval or rejection (with the reason, if given), and an "Account approved" alert waiting at first sign-in
- Registration status page behind a signed, expiring link that updates itself every 30 seconds, for when self-registration is on (`docs/explain/registration-status.md`)
- Log in with the Baze email only, for students and staff alike (D-41); the student ID and internal usernames no longer sign in; superusers receive the application administrator role; an eye button shows or hides any password field
- Administrator-created staff accounts with a one-time temporary password and a forced password change at first sign-in; administrators can correct a staff member's Baze email (their own too), which moves the sign-in and is audited
- Student accounts in Admin tools: search by name, Baze email or student ID; correct name, Baze email, student ID and programme (not once a project exists); reset a forgotten password; deactivate or reactivate (never bypassing approval); all audited
- **My details** (`/account/contact/`) for every account: personal email and phone, each with its own visibility (only me, staff only, all signed-in users); shown on project pages for the student and the supervisor; current students without a personal email are reminded to add one
- The HOD appoints the FYP coordinator and the staff allowed to assign supervisors (D-19)
- Login and logout (logout is POST only), role-based dashboard
- Logged-out welcome page (`/`): live totals (archived and running projects, academic staff, faculties; real rows only, sample rows only on a demo-only database), how a project moves through the hub, and a tile per faculty; visitors' header shows Home, How it works, Faculties, Past research and one highlighted **Log in**; signing out lands on the welcome page (D-39)
- The Baze University crest is the header brand on every page (`static/img/baze-logo.png`, "BU" if the file is missing); the login form sits on the left over a background picture
- Glass look by default (`UI_THEME=glass`), with the classic look one setting away (D-35)
- Separate portals and role-aware navigation for current students, alumni, supervisors, coordinators, HODs and system administrators
- `role_required` permission helper (deny by default)

### Academic structure and repository
- Faculty → Department → Programme models, with a management page for administrators
- Authenticated project repository with Current/Past sections, search, academic filters and role-aware project detail pages
- Permission-checked project downloads with per-file Baze-user/staff visibility and extension/size validation
- Admin-only CSV import of historic project summaries, all or nothing: every bad row is listed with its line number and nothing is saved until every row is valid; supervisors and previous supervisors must be academic staff of the project's department. Demo sample: `docs/sample_import.csv`
- Similar-topic checker: archived projects whose topics score above `SIMILARITY_THRESHOLD` are listed (`docs/explain/similarity.md`)
- Search filters: the Year filter opens a calendar-style year grid (years with projects clickable); a Semester filter beside it (D-38)
- Archived files show who uploaded them; earlier supervisors are listed once each and never repeat the final supervisor
- A file missing from disk shows a plain "not available" page (404) instead of a server error, and is logged

### Project workflow and supervision
- The proposal shows only the fields the supervisor's method needs, can be saved as a draft, opens with what was saved, and stays editable until the supervisor decides (D-36)
- Student project creation and a role-checked proposal-to-HOD-archive workflow, with per-supervisor approval criteria, decision snapshots and status history
- Students upload proposal and final report files; the project cannot be submitted until a final report is present
- The department's coordinator can also upload the final document for a project in their department (in progress, submitted or defended), from "Upload final report" on the workflow page. The file is recorded under the coordinator and audited; the HOD's sign-off still archives the project and moves its files
- Staff who may open a running project's files see them listed on its workflow page, newest first, with type, uploader and date
- Screenshots (up to 6) and demo videos (up to 2, upload or YouTube/Drive/Vimeo link) on running and archived projects, content-checked and permission-served; they move to the archive at sign-off (D-30)
- HOD sign-off, archive and convocation list (printable and CSV); ticking "Graduation verified" needs the graduation year (D-40)
- Semesters typed by hand (26A, 26B, 26C): the coordinator (or an admin) types a project's semester at allocation or on its workflow page, and a new code is added the first time it is used (checked: two digits and A, B or C; "26 a" becomes 26A); **Semesters** is for noting dates or correcting a code; search and the convocation list take a typed semester, with the codes in use as suggestions; faculty deadlines can be tied to a semester; the archive keeps the semester; convocation list and CSVs show it; older records stay "Not set" until someone fills them in (D-38)
- Project list CSV for coordinators (faculty), HODs (department) and administrators (all), audited (D-34)
- Student allocation lists students who have no supervisor yet (a coordinator sees and allocates across their whole faculty, D-29); allocating creates their project record ("Topic to be agreed"). Supervisors are offered least busy first with their load; a change of supervisor needs a reason (D-27)
- Department-scoped supervisor assignment and reassignment for individually authorised staff, with a history recording who changed it, when, and why; supervisor workload counts in the assignment workspace
- Staff supervision history shows each staff member's current supervisees, prior assignments and archived supervisees; student-only My Project is hidden and denied to staff
- Supervisor meeting scheduling and records, held/missed counts, student confirmation/dispute, and versioned edits
- Weekly supervisor availability windows; students request a meeting in a window and the supervisor accepts (it becomes a scheduled meeting) or declines with a reason; both are alerted (D-32)
- Department/project notices with first-seen and acknowledgement timestamps (the author is not asked to acknowledge their own notice); shared supervisor resources with permission-checked downloads
- Faculty deadlines set by the coordinator become milestones on every running project; supervisors add per-student milestones and mark them done; students are reminded three days before (D-33)
- Supervisor-provided documents on the Project guide: the department's FYP report instructions and template (PDF and Word), downloadable by every signed-in student and staff member, never by the public
- Project health score with reasons, shown only to the roles allowed to see it (`docs/explain/health-score.md`)

### Alerts, automation and live counters
- Every alert also emailed once to the Baze email (D-31)
- In-app alerts with an unread count in the menu, mark one or all as read, and no duplicate of the same alert within 24 hours
- `run_automation` (once, from a scheduler, or with `--loop`): flags at-risk projects, registrations waiting too long and unacknowledged notices (`docs/explain/automation.md`)
- Live counters from `/api/summary/`, polled every 30 seconds while the tab is visible (`docs/explain/live-counters.md`)

### Audit, admin and demo
- One admin hub, **Admin tools** (`/admin-tools/`): the only page linking to the audit log, CSV import, academic structure and Django administration; the audit log and CSV import are admin-only
- The Django admin cannot bypass the workflow (`docs/explain/admin-integrity.md`): a project's stage, stage dates, archived flag and supervisor are read-only, and a project cannot be deleted there (singly or in bulk). Status events, supervisor assignments, approval decisions, approval forms, completions, meeting records with their versions, and audit events are view-only (no add, change or delete)
- Admin-only audit log screen with readable labels and "Field: before -> after" changes
- Audit events are append-only at the database level: triggers on `audit_auditevent` refuse every UPDATE and DELETE (created on MySQL and SQLite; `apps/audit/migrations/0003_append_only_triggers.py`). This is the only table with triggers
- Project status events and approval decisions are also append-only in the model (the model and its queryset refuse update and delete). Supervisor assignments change only through the audited assignment workflow; their model has no append-only guard
- `seed_demo` and `purge_demo` commands (demo rows flagged `is_demo` and shown with a "Sample" tag, not "(demo)" in names; seeded downloads are real PDFs made at seed time); the demo runs on its own SQLite database (`SQLITE_PATH`) through `run_demo.ps1`
- Live counters and the lists beside them follow the viewer: a demo account counts demo and real rows, a real account real rows only

## Verification status
- `manage.py test apps`: **356 tests pass on SQLite (`DB_ENGINE=sqlite`) and on MySQL 8.4** (2026-10-13).
- `apps/accounts/tests_docs.py` checks that every row of `docs/code_map.md` names a real file and name.
- Runtime in use: Python 3.14.0, Django 5.2.18, MySQL 8.4.

## Run it on Windows (Python 3.14, MySQL 8.4)
1. Open a terminal in this folder, then:
   `py -3.14 -m venv .venv` → `.venv\Scripts\activate` → `pip install -r requirements.txt`
2. In MySQL Workbench (as root) run:
   ```sql
   CREATE DATABASE baze_projecthub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'projecthub_app'@'localhost' IDENTIFIED BY 'choose-a-password';
   GRANT ALL PRIVILEGES ON baze_projecthub.* TO 'projecthub_app'@'localhost';
   GRANT ALL PRIVILEGES ON `test\_baze\_projecthub`.* TO 'projecthub_app'@'localhost';
   SET PERSIST log_bin_trust_function_creators = 1;
   ```
   The last line lets the application account create the audit triggers (see the repository README, "MySQL setup").
3. Copy `.env.example` to `.env`, set `DB_PASSWORD` and a long random `DJANGO_SECRET_KEY`.
4. `python manage.py migrate`
5. `python manage.py runserver` → open http://127.0.0.1:8000/
6. `python manage.py test apps`

For the demo, run `.\run_demo.ps1` from the repository root instead. It uses its own SQLite database and leaves MySQL untouched. Demo accounts use the password `ChangeMe123!` (for example `demo.admin`, `demo.coordinator`, `demo.amina`).

## Still outstanding

### Remaining Django admin gaps
- Milestones and project documents can still be added, changed and deleted in the Django admin (inlines on a project, and the Project documents screen).
- Deleting a student account: the Django admin refuses once the student has a project, because the delete would take records the admin may not delete (403, or a "no permission" page). A student without a project can still be deleted there.
- On MySQL, the Django admin's meeting list (`/admin/supervision/supervisionmeeting/`) fails with "Database returned an invalid datetime value. Are time zone definitions for your database installed?". Its `date_hierarchy` needs MySQL's time zone tables, which this server does not have (`TIME_ZONE` is `Africa/Lagos`, `USE_TZ` is on). It fails the same way before and after the meeting records became view-only. Fix by loading MySQL's time zone tables or by removing `date_hierarchy`.
- Outside the admin (shell or code), deleting a student cascades to their projects and every workflow record on them (`Project.student` is `CASCADE`). It is blocked with `ProtectedError` only when the student is the actor of an audit event (`AuditEvent.actor` is `PROTECT`) or has an archived project (`ArchivedProject.student` is `PROTECT`).

### Known limits (from `docs/known_limits.md`)
- Multiple supervisors per project (co-supervision) is planned, not built: each project has one current supervisor, and earlier supervisors are kept in its history.
- Semesters are not deleted in the app. `seed_demo` adds 26A, 26B and 26C and spreads the running demo projects over 26A and 26B; past demo projects stay "Not set".
- No "corrections required" loop after a defence; stages only move forward (R-11).
- No email verification at registration; an administrator approves each registration by hand.
- Running project files are listed for staff on the workflow page only (with type, uploader and date); the project summary page does not list them.
- Milestones cannot be created or edited in the app, only in the Django admin.
- `SupervisionLogEntry` (running log) has no screens.
- No pagination on the repository.
- The Django admin shows every model to superusers, including meeting records that the app itself restricts (R-33). Meeting records are view-only there now, but still visible.

### Open questions for the supervisor (from `docs/decisions.md` section C)
- Q-01: what "make it unique" means, with examples.
- Q-02: whether the project approval form is signed, and whether the title must be fixed first.
- Q-04: whether student names, IDs and contact details appear in the repository, and whether consent is needed. Built meanwhile as the author's interim answer (D-21): IDs staff-only, each contact detail opt-in.
- Q-05: whether Baze already has a repository or supervision tool.
- Q-06: whether MySQL/Workbench is required for all projects, and other written defence requirements.
- Q-07: the department's exact approval chain (who signs, in which order). Confirm before hard-coding approval policy.
- Q-08: what the department expects at the defence: a working system, a comparison, or both.
- Q-09: an anonymised sample of the paper forms, to copy the form fields.
- Q-10: whether a corrections-required step is needed after the defence, and who clears it.
- Q-11: what "too much for now" meant about the other supervision project.

Q-03 (repository audience) is answered: signed-in Baze Project Hub users only.

## Notes
- Django models are the source of truth. `docs/database_schema.sql` is an early design reference, and its table names do not match the Django tables.
- Demo accounts exist for development only. `seed_demo` refuses to run when `DJANGO_DEBUG=False` unless you pass `--force`.
- All documentation is in the repository-root `docs/` folder; start at `docs/README.md`.
