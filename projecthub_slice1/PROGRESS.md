# Progress

**Last updated:** 2026-10-05 · **Core workflows implemented; hardening and academic deliverables remain**

## Implemented
- Django 5.2 project, settings read from environment or `.env`
- MySQL connection (utf8mb4); SQLite option for a quick tryout
- Custom user model with roles: student, supervisor, coordinator, HOD, admin
- Student and supervisor profiles (student number, programme, consent flag, student status)
- Student registration with Baze email and student ID, pending administrator review, and approve/reject actions
- Sign-in with Baze email, student ID, or staff username; superusers receive the application administrator role
- Faculty → Department → Programme models and admin screens
- Login and logout (logout is POST only), role-based dashboard
- Separate portal experiences and role-aware navigation for current students, alumni, supervisors, coordinators, HODs and system administrators
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
- Student project creation and a role-checked proposal-to-HOD-archive workflow, with per-supervisor approval criteria, decision snapshots, and status history
- Students can upload proposal and final report files; the project cannot be submitted until a final report is present
- Supervisor meeting scheduling and records, held/missed counts, student confirmation/dispute, and versioned edits
- Weekly supervisor availability with student meeting requests and supervisor approval into a scheduled meeting
- Department/project notices with first-seen and acknowledgement timestamps
- Admin-only audit log screen and read-only audit events for key workflow, assignment, notice, meeting and account actions
- Admin-only CSV import of historic project summaries with row-level errors

## Verification status
- `manage.py check`: no issues (SQLite).
- `manage.py makemigrations --check --dry-run`: no model changes missing migrations.
- `manage.py test apps`: all 41 tests pass (SQLite), including role-specific portal and student/alumni routing tests.
- Browser smoke checks from the earlier repository slice are documented below; the role portals still need an interactive visual review.

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

## Still outstanding
- Shared resource upload and publication screen for supervisor materials; project documents can be uploaded by students and admins.
- Student upload workflow for project documents; current document upload is through Django Admin.
- A corrections-required stage, if the department confirms it is needed.
- Database-level audit immutability (MySQL privileges/triggers); application audit screens are read-only.
- MySQL integration run and browser smoke test of the new workflow pages.
- Confirm the approval chain, consent rules, final title, signed approval form and open questions in `docs/decisions.md`.
- Academic report, diagrams, backup/restore procedure, and usability/evaluation evidence remain separate deliverables.

## Open items that affect later slices
See `docs/decisions.md` section C. Q-03 (repository audience) is answered; Q-07 (the department's exact approval chain) remains open and should be confirmed before hard-coding approval policy.

## Notes
- Django models are the source of truth. `docs/database_schema.sql` is a design reference; slice 1 implements only users, profiles and the academic structure from it.
- Demo accounts exist for development only. `seed_demo` refuses to run when `DJANGO_DEBUG=False` unless you pass `--force`.
