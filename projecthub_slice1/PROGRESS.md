# Progress

**Last updated:** 2026-10-05 · **Repository and project discovery slice implemented**

## Implemented
- Django 5.2 project, settings read from environment or `.env`
- MySQL connection (utf8mb4); SQLite option for a quick tryout
- Custom user model with roles: student, supervisor, coordinator, HOD, admin
- Student and supervisor profiles (student number, programme, consent flag, student status)
- Student registration with Baze email and student ID, pending administrator review, and approve/reject actions
- Sign-in with Baze email, student ID, or staff username; superusers receive the application administrator role
- Faculty → Department → Programme models and admin screens
- Login and logout (logout is POST only), role-based dashboard
- `role_required` permission helper (deny by default)
- Staff-only academic structure page; admin-only tools page
- `seed_demo` and `purge_demo` commands (demo rows flagged `is_demo`)
- Authenticated project repository with Current/Past sections, search, academic filters and role-aware project detail pages
- Permission-checked project downloads with per-file Baze-user/staff visibility and extension/size validation
- Department-scoped supervisor assignment and reassignment for individually authorized staff (the responsibility can be granted to a supervisor, HOD, coordinator or other eligible staff), plus a history recording who changed it, when, and why
- Staff supervision history shows only each staff member's current supervisees, prior assignments and archived supervisees; student-only My Project is hidden and denied to staff
- Supervisor workload counts in the assignment workspace; direct Django Admin editing of a project's supervisor is disabled so changes use the audited workflow
- Synthetic sample projects in the demo seed, removed by demo purge
- Automated tests cover account roles/registration, repository search/filtering/privacy, secure downloads, assignment permissions/history, demo seed/purge, and unique student IDs

## Tested
- `manage.py test apps`: all 39 tests pass on SQLite.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no model changes missing migrations.
- Browser smoke checks: repository showed four current and two past sample projects; coordinator navigation omits My Project; Supervision history and Approvals render without URL errors.

## Run it on Windows (Python 3.12, MySQL 8.4)
1. Unzip, open a terminal in the folder, then:
   `py -3.12 -m venv .venv` → `.venv\Scripts\activate` → `pip install -r requirements.txt`
   (If `mysqlclient` fails to install, tell me the error text.)
2. In MySQL Workbench (as root) run:
   ```sql
   CREATE DATABASE baze_projecthub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'projecthub_app'@'localhost' IDENTIFIED BY 'choose-a-password';
   GRANT ALL PRIVILEGES ON baze_projecthub.* TO 'projecthub_app'@'localhost';
   GRANT ALL PRIVILEGES ON `test\_baze\_projecthub`.* TO 'projecthub_app'@'localhost';
   ```
3. Copy `.env.example` to `.env`, set `DB_PASSWORD` and a long random `DJANGO_SECRET_KEY`.
4. `python manage.py migrate`
5. `python manage.py seed_demo` (prints the demo password)
6. `python manage.py runserver` → open http://127.0.0.1:8000/
7. `python manage.py test apps`

Local demo login: `demo.amina` / `ChangeMe123!` (also `amina@bazeuniversity.edu.ng` or `BU/22/CS/4012`). `demo.admin` can open `/admin/`.

## Git
Commit this folder as your first commit. `.env` is ignored. Keep each future slice as its own commit.

## Next
- Department-specific approval form and project status transitions
- Supervision meeting records, attendance confirmation, notices and version history
- HOD completion sign-off and archive transition
- Public-facing document-upload workflow (current documents are administered through Django Admin)

## Open items that affect later slices
See `docs/decisions.md` section C. Q-03 (repository audience) is answered; Q-07 (the department's exact approval chain) remains open and should be confirmed before hard-coding approval policy.

## Notes
- Django models are the source of truth. `docs/database_schema.sql` is a design reference; slice 1 implements only users, profiles and the academic structure from it.
- Demo accounts exist for development only. `seed_demo` refuses to run when `DJANGO_DEBUG=False` unless you pass `--force`.
