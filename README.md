# Baze Project Hub

A Django application for managing final-year project accounts, supervision, approvals, and the project repository.

The active application is in [`projecthub_slice1`](./projecthub_slice1/). It is the only application in this repository.

## Where things are

| Path | What it holds |
|---|---|
| [`projecthub_slice1/`](./projecthub_slice1/) | The Django project: `manage.py`, `config/` (settings, URLs), `apps/`, `templates/`, `static/`, `requirements.txt`, `.env.example` |
| [`projecthub_slice1/apps/`](./projecthub_slice1/apps/) | `accounts`, `academics`, `projects`, `supervision`, `audit` |
| [`projecthub_slice1/PROGRESS.md`](./projecthub_slice1/PROGRESS.md) | What is done and what is outstanding |
| [`docs/`](./docs/) | All documentation; start at [`docs/README.md`](./docs/README.md) |
| [`docs/code_map.md`](./docs/code_map.md) | Where to change what |
| `run_tests.ps1`, `run_demo.ps1` | Run the tests on SQLite; run the demo on its own SQLite database |

Runtime versions in use: **Python 3.14.0**, **Django 5.2.18**, **MySQL 8.4**. The virtual environment is `projecthub_slice1\.venv`.

## Run the automated tests

From PowerShell at the repository root:

```powershell
.\run_tests.ps1
```

The script runs the Django tests against SQLite.

## Run the demo

The demo story (21 synthetic projects, health-score bands, a similar archived topic) lives in its own SQLite database, `projecthub_slice1/demo.sqlite3`, so the real MySQL database stays clean. From PowerShell at the repository root:

```powershell
.\run_demo.ps1          # build the demo if needed, then serve it on http://127.0.0.1:8000/
.\run_demo.ps1 -Fresh   # start the demo over
```

All demo accounts use the password `ChangeMe123!` (for example `demo.admin`, `demo.coordinator`, `demo.okoro`, `demo.amina`). Stop the real server first: both use port 8000.

## Run the application locally

The real system uses MySQL (settings in `projecthub_slice1/.env`). To try it on a throwaway SQLite database instead, from PowerShell:

```powershell
cd .\projecthub_slice1
$env:DB_ENGINE = "sqlite"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo --force
.\.venv\Scripts\python.exe manage.py runserver
```

Open <http://127.0.0.1:8000/> in a browser.

For local testing, sign in as `demo.amina` with password `ChangeMe123!`. The Amina demo account can also sign in with `amina@bazeuniversity.edu.ng` or student ID `BU/22A/CS/4012`. Open **Repository** to see synthetic current and past project records. Demo accounts and projects are clearly labelled test fixtures, not real university accounts or project submissions.

**Deadlines and milestones:** the coordinator sets common deadlines for the faculty under **Deadlines** (e.g. "Chapter 1" due 15 March). Each one becomes a milestone on every running project of the faculty, and on projects started later. On a project's **Milestones** page the supervisor adds extra milestones for that student and marks any milestone done; the student, the coordinator and the HOD can read it. Students are reminded three days before a due date (alert and email), and overdue milestones raise the project's health score.

**Meetings:** supervisors publish weekly availability windows. On **Supervision meetings**, a student requests a meeting in one of those windows (a date on that day and an optional note); the supervisor accepts it, which schedules the meeting, or declines with a reason. Both are alerted, by email too. A time that already has a meeting cannot be requested.

**Screenshots and demo videos:** a student adds up to 6 screenshots (JPG, PNG or WebP, 5 MB each) and up to 2 demo videos (an MP4/WebM upload up to 100 MB, or a YouTube, Google Drive or Vimeo link) from **My project → Add screenshot or video**. While the project runs, only the student, their supervisor, staff of the department and administrators see them; at HOD sign-off they move to the archived project with its files, where every signed-in Baze user sees them (or staff only, if the student chose that). Administrators can add media to archived projects. Files are type- and content-checked and served only through a permission check.

Sample files for past projects can be added through Django Admin under **Project documents**. Select one project parent, choose the visibility, and attach an allowed PDF/Office/ZIP file (maximum 25 MB). Student downloads are restricted to files marked for all signed-in Baze users; staff-only files remain staff-only. Never expose the `media` directory through an unauthenticated static-file server.

Staff given the assignment permission can open **Student allocation** to give students a supervisor and to change supervisors. A coordinator works across their whole **faculty**, whatever their own teaching field: they see the faculty's students and projects and can choose any supervisor in the faculty. A supervisor or HOD given the permission stays within their own department. Students who have no project yet are listed under **Students waiting for a supervisor**: choosing a supervisor creates their project record ("Topic to be agreed"), and their proposal sets the real title later. Supervisors are listed least busy first, with their current number of students, so the load stays even. A coordinator or HOD can choose themself. Changing an existing supervisor needs a reason (for example "Student asked: wants a supervisor in AI"); the coordinator decides, and every change keeps an audited history. An administrator grants this permission to the appropriate coordinator, supervisor or HOD.

To try that staff workflow locally, sign in as `demo.coordinator` with password `ChangeMe123!`; this demo coordinator has assignment permission and is scoped to the sample Computer Science department.

## Account access

- **Students do not create their own accounts.** The FYP coordinator (for any programme of their faculty) or the administrator adds each final-year student under **Add student**: name, `@bazeuniversity.edu.ng` email, full student ID (for example `BU/23B/IT/7892`: Baze University, year 23, batch B, department IT, number 7892), programme and status. The account is active at once; a temporary password is shown once, and the student chooses their own at first sign-in. This keeps accounts to students the department has checked are ready for their FYP.
- Everyone signs in with their Baze email; students can also use their full student ID. The short number alone (`7892`) is not accepted, because another year or department can have the same number.
- Self-registration still exists but is **off** (`STUDENT_SELF_REGISTRATION=False`). If a department switches it on in `.env`, registrations wait for an administrator's approval, the student is emailed the decision, and a status page shows the outcome.
- Every in-app alert is also emailed once to the person's Baze email (`EMAIL_ALERTS`, on by default; never to demo accounts); `SITE_URL` makes the link in the email absolute.
- Email settings live in `projecthub_slice1/.env` (see `.env.example`). Without them, emails are printed in the server terminal instead of being sent, which is fine for development; at launch, add the SMTP details from Baze ICT.
- Staff and administrator accounts are created only by an administrator.
- Create the initial administrator with `python manage.py createsuperuser`. The account is assigned the administrator role automatically. If its password is forgotten, reset it with `python manage.py changepassword <username>`.
- The administrator adds supervisor, coordinator, HOD and further administrator accounts in **System administration → Add staff account**. A temporary password is shown once; the person must choose their own at first sign-in. The same page per staff member edits name, Baze email, role and department, resets the password, and deactivates or reactivates the account. Correcting the Baze email (for example a typo, or the demo address `admin@bazeuniversity.edu.ng`) moves the sign-in to the new address, is audited, and sends a notice to it.
- Assignment access is a separate staff permission, not a job title: tick **Can assign supervisors in their department** on the staff account. A supervisor or HOD may supervise projects and can be delegated the allocation responsibility independently.
- Everyone (students, alumni and staff) keeps their own contact details under **My details** (`/account/contact/`): a personal email and a phone number, each with its own choice of who sees it (only me, staff only, or all signed-in Baze users). People cannot change their own Baze email there; an administrator corrects it if it is wrong. A personal email matters most for alumni, whose Baze address may close after graduation.
- When someone entered wrong details or forgot their password, the administrator fixes it. Staff: open them from the staff list in **System administration**. Students: search by name, Baze email or student ID under **Student accounts** on the same page, then correct their name, Baze email, student ID or programme, reset a forgotten password, or deactivate or reactivate the account. Every change is audited.
- Every password field has an eye button to show or hide the password while typing.
- Local demo users are created with `seed_demo` and removed with `purge_demo`.

## MySQL setup

The audit log is protected by database triggers (`apps/audit/migrations/0003_append_only_triggers.py`). With binary logging on (the MySQL 8 default), MySQL only lets an account without `SUPER` create triggers when this server setting is enabled. Run it once as `root`; `PERSIST` keeps it across server restarts:

```sql
SET PERSIST log_bin_trust_function_creators = 1;
```

Without it, `migrate` on a fresh database and the MySQL test run fail with *"You do not have the SUPER privilege and binary logging is enabled"*. An already-migrated database keeps working either way.

## Repository hygiene

`.gitignore` excludes virtual environments, local `.env` files, SQLite databases, Python caches, and editor-specific files. Never commit university account credentials or student records.
