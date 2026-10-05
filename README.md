# Baze Project Hub

A Django application for managing final-year project accounts, supervision, approvals, and the project repository.

The active application is in [`projecthub_slice1`](./projecthub_slice1/). It is the only application in this repository.

## Run the automated tests

From PowerShell at the repository root:

```powershell
.\run_tests.ps1
```

The script runs the Django tests against SQLite.

## Run the application locally

From PowerShell:

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
- Staff and administrator access is not self-registerable; accounts must be provisioned by an administrator.
- Create the initial administrator with `python manage.py createsuperuser`. The account is assigned the administrator role automatically; use Django Admin to add other staff accounts.
- Assignment access is a separate staff permission, not a job title. In Django Admin, edit the relevant staff account and enable **Can assign supervisors**; it will be scoped to that staff member's department. A supervisor or HOD may supervise projects and can be delegated the allocation responsibility independently.
- Local demo users are created with `seed_demo` and removed with `purge_demo`.

## Repository hygiene

`.gitignore` excludes virtual environments, local `.env` files, SQLite databases, Python caches, and editor-specific files. Never commit university account credentials or student records.
