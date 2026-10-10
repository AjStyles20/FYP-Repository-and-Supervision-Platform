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

For local testing, sign in as `demo.amina` with password `ChangeMe123!`. The Amina demo account can also sign in with `amina@bazeuniversity.edu.ng` or student ID `BU/22/CS/4012`. Open **Repository** to see synthetic current and past project records. Demo accounts and projects are clearly labelled test fixtures, not real university accounts or project submissions.

Sample files for past projects can be added through Django Admin under **Project documents**. Select one project parent, choose the visibility, and attach an allowed PDF/Office/ZIP file (maximum 25 MB). Student downloads are restricted to files marked for all signed-in Baze users; staff-only files remain staff-only. Never expose the `media` directory through an unauthenticated static-file server.

Staff given the assignment permission can open **Student allocation** to assign or reassign supervisors for active projects in their department. An administrator grants this permission to the appropriate coordinator, supervisor or HOD. Assignment changes keep an audit history.

To try that staff workflow locally, sign in as `demo.coordinator` with password `ChangeMe123!`; this demo coordinator has assignment permission and is scoped to the sample Computer Science department.

## Account access

- Current and past final-year students can submit a registration using a `@bazeuniversity.edu.ng` email, student ID, programme, and password.
- New student accounts stay inactive until an administrator reviews the registration.
- The student is emailed at their Baze address when the registration is approved or rejected (with the reason, if the administrator gives one). Signing in with the right password before then shows whether the registration is still pending or was not approved.
- Email settings live in `projecthub_slice1/.env` (see `.env.example`). Without them, emails are printed in the server terminal instead of being sent, which is fine for development; at launch, add the SMTP details from Baze ICT.
- Staff and administrator access is not self-registerable; accounts must be provisioned by an administrator.
- Create the initial administrator with `python manage.py createsuperuser`. The account is assigned the administrator role automatically. If its password is forgotten, reset it with `python manage.py changepassword <username>`.
- The administrator adds supervisor, coordinator, HOD and further administrator accounts in **System administration → Add staff account**. A temporary password is shown once; the person must choose their own at first sign-in. The same page per staff member edits role and department, resets the password, and deactivates or reactivates the account.
- Assignment access is a separate staff permission, not a job title: tick **Can assign supervisors in their department** on the staff account. A supervisor or HOD may supervise projects and can be delegated the allocation responsibility independently.
- Local demo users are created with `seed_demo` and removed with `purge_demo`.

## MySQL setup

The audit log is protected by database triggers (`apps/audit/migrations/0003_append_only_triggers.py`). With binary logging on (the MySQL 8 default), MySQL only lets an account without `SUPER` create triggers when this server setting is enabled. Run it once as `root`; `PERSIST` keeps it across server restarts:

```sql
SET PERSIST log_bin_trust_function_creators = 1;
```

Without it, `migrate` on a fresh database and the MySQL test run fail with *"You do not have the SUPER privilege and binary logging is enabled"*. An already-migrated database keeps working either way.

## Repository hygiene

`.gitignore` excludes virtual environments, local `.env` files, SQLite databases, Python caches, and editor-specific files. Never commit university account credentials or student records.
