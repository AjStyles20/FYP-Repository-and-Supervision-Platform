# Defence Q&A: Baze Project Hub

Likely examiner questions, with a short answer to say aloud, how it works, where it is in the code, and how to show it live. Paths are relative to `projecthub_slice1/`. Keep this file up to date when a feature changes.

**How to use it:** learn the *Say* line for each question; read *How it works* until you could draw it; rehearse *Show it* once on the demo data.

---

## Accounts, roles and access

### 1. How do people get accounts? Can anyone become an administrator?

**Say:** "Students register themselves, but their accounts stay inactive until an administrator approves them. Staff cannot register at all: an administrator creates their accounts. The very first administrator is created on the server with `createsuperuser`, so nobody can make themselves an admin through the website."

**How it works:**
- `StudentRegistrationForm` (`apps/accounts/forms.py`) always creates role **student**, `is_active=False`, registration status **pending**. It has no role field, and a test posts a forged `role=admin` to prove it is ignored.
- Admin approves or rejects in **System administration** (`review_student_registration` in `apps/accounts/views.py`); both are audited.
- Staff accounts: **System administration → Add staff account** (`add_staff_account`).
- First admin: `python manage.py createsuperuser`. The custom manager (`ProjectHubUserManager.create_superuser` in `apps/accounts/models.py`) sets role = administrator.

**Show it:** the sign-up page (no role choice, "Staff?" note) → sign in as admin → Add staff account.

### 2. How was the temporary password `BYmt7BHmQ5Qng6p2` made, and is it safe?

**Say:** "It is 12 bytes from the operating system's cryptographically secure random generator, encoded as 16 URL-safe characters: 96 bits, so it cannot be guessed. The database stores only a salted PBKDF2 hash. The password is shown once on a page the browser is told not to cache, it is never logged, and the person must replace it at first sign-in."

**How it works:**
1. `generate_temporary_password()` → `secrets.token_urlsafe(12)` (`apps/accounts/forms.py`). `secrets` uses the OS CSPRNG; the `random` module would be predictable and must not be used for passwords.
2. 12 bytes = 96 bits ≈ 7.9 × 10²⁸ possibilities; Base64url turns them into 16 characters from A–Z a–z 0–9 `-` `_`.
3. `create_user(password=...)` stores a **PBKDF2-SHA256** hash: random salt per user, **1,000,000 iterations** (Django 5.2 default). The plain password is never stored, which is also why a forgotten password must be *reset*, not *looked up*.
4. The result page is rendered directly (no redirect, so no flash message or cookie holds it) with `Cache-Control: no-store`. The audit entry records role and department only; a test checks the password is absent.
5. `must_change_password = True` + `ForcePasswordChangeMiddleware` (`apps/accounts/middleware.py`) send the user to **Choose your password** on every page until they set their own.

**Show it:** create a test supervisor → copy the password → private window → sign in → forced to choose a password.

### 2b. How does a student know their registration was approved?

**Say:** "They get an email at their Baze address when the administrator approves or rejects it, with the reason if it was rejected. And if they try to sign in before then with the right password, the login page tells them it is still awaiting approval. A wrong password only gets the general error, so nobody can use the login page to find out who has registered."

**How it works:** `_email_registration_decision` in `apps/accounts/views.py` sends the email with Django's `send_mail`; if the mail server is down, the decision is still saved and the admin is warned to tell the student directly. `ProjectAuthenticationForm._inactive_account_message` in `apps/accounts/forms.py` checks the password before revealing any status. In development the email backend prints messages in the server terminal; at launch the SMTP settings go in `.env`.

**Show it:** register a test student → sign in with the right password ("still awaiting approval") → approve as admin → the email appears in the server terminal → the student signs in.

### 3. How do you stop a user opening pages for another role?

**Say:** "Every non-public view is protected on the server by a `role_required` decorator: deny by default, 403 for the wrong role, the login page for anyone signed out. Hiding a menu link is never the protection."

**How it works:** `role_required(*roles)` in `apps/accounts/permissions.py` wraps `login_required` and checks `request.user.role`. Object-level checks go further: a supervisor can only open workflows for projects they supervise, a coordinator only their department's (`project_workflow` in `apps/projects/views.py`). File downloads return 404, not 403, for files outside your department, so an ID does not even confirm a file exists (`download_project_document`).

**Show it:** sign in as a student and type `/admin-tools/` in the address bar → 403 page.

### 3b. Who does what: supervisor, FYP coordinator, HOD, administrator?

**Say:** "It follows how Baze works. Supervisors accept topics against their own criteria and supervise. The FYP coordinator, a lecturer the HOD appoints, logs the signed approval form and records defences. The HOD does HOD work: signs off when the student brings the final documents, which archives the project, and keeps the convocation list. The administrator only manages accounts and setup and sees no supervision material. Allocating supervisors is a permission the HOD gives to chosen lecturers, not a job title."

**How it works:** stage rules in `TRANSITION_ROLES` (`apps/projects/services/lifecycle.py`); the coordinator-only check in `log_approved_form` (`apps/projects/services/approval.py`); the HOD's *Department staff* page (`department_staff` in `apps/accounts/views.py`) can only switch lecturers in their own department between supervisor and coordinator and grant the allocation permission; the HOD's queue shows only defended projects; the *Convocation list* (`convocation_list` in `apps/projects/views.py`) prints or downloads as CSV, with spreadsheet-formula protection, and every download is audited. Decision D-19.

**Show it:** sign in as the HOD → Department staff → make a lecturer the FYP coordinator → Convocation list → Download.

### 4. Can an administrator lock everyone out?

**Say:** "No. You cannot deactivate or demote yourself, and the last active administrator cannot be deactivated or demoted by anyone. If all else fails, `createsuperuser` and `changepassword` on the server always work."

**How it works:** `StaffEditForm.clean()` and `manage_staff_account` (`apps/accounts/forms.py`, `views.py`) use `active_admin_count()`. Tests: `test_an_admin_cannot_lock_themselves_out`, `test_the_last_active_admin_cannot_be_removed_by_another_admin`.

### 5. What happens when a staff member leaves?

**Say:** "The administrator deactivates the account. They can no longer sign in, any open session ends on their next click, and nothing is deleted: their projects, meetings and audit history stay. The page warns if they still supervise active projects so those can be reassigned first."

**How it works:** `is_active=False`; Django's authentication backend refuses inactive users on every request. Test: `test_deactivation_ends_an_open_session`.

---

## Records you can trust

### 6. How do you know nobody edited the history?

**Say:** "History is added to, never overwritten. Project status events and approval decisions are refused at the model and queryset level if anything tries to update or delete them. Supervisor assignments are never overwritten either: a change closes the current row and adds a new one with the reason, although that model has no append-only guard of its own. The audit log has a third layer: database triggers, on MySQL and on SQLite, refuse UPDATE and DELETE even from direct SQL."

**How it works:**
- Model and QuerySet guards raise `PermissionError` on update/delete (`apps/projects/models/project.py`, `approval.py`, `apps/audit/models.py`).
- Triggers on `audit_auditevent` (`apps/audit/migrations/0003_append_only_triggers.py`) block UPDATE and DELETE at the database level. They are created on MySQL and on SQLite, so the SQLite test run exercises them too.
- A supervisor change goes through `assign_project_supervisor` (`apps/projects/services/assignment.py`): it sets `ended_at` on the current row, adds a new row with `change_reason`, and writes an audit event with the reason.
- Meeting records keep every edit as a version (`MeetingRecordEdit`) and both student and supervisor confirm or dispute them.
- The Django admin shows all of these records read-only: no add, change or delete (`apps/projects/admin.py`, `apps/supervision/admin.py`, `apps/audit/admin.py`).

**Show it:** a workflow page's *Approval decisions* list (Adaeze's declined then accepted proposal) and the Audit log.

**Be ready for:** "Is anything not protected?" — see Q16-19: the Django admin can no longer change a project's stage, dates or archived flag, but milestones and documents are still editable there, and deleting a student outside the admin cascades. The triggers are not absolute either: Q17 explains that the app account, with the documented grant, could drop them.

### 7. Why did MySQL need `SET PERSIST log_bin_trust_function_creators = 1`?

**Say:** "MySQL 8 has binary logging on by default, and then it only lets an account with the SUPER privilege create triggers. Our app account deliberately does not have SUPER, so the server setting allows it. `PERSIST` keeps it across restarts."

**How it works:** without it, creating the audit triggers fails with *"You do not have the SUPER privilege and binary logging is enabled"*. Documented in the README's *MySQL setup* section.

### 8. How do you guarantee a project has only one current supervisor?

**Say:** "The database enforces it, not just the code. Each assignment row has an `is_current` flag that is True while open and NULL when ended. A unique constraint on (project, is_current) allows any number of ended rows, because NULLs never clash, but only one current row. That works on MySQL, which has no partial unique indexes."

**How it works:** `ProjectSupervisorAssignment` (`apps/projects/models/assignment.py`), plus a check constraint keeping `is_current` and `ended_at` consistent. Test: `test_second_current_supervisor_is_rejected_by_the_database`.

---

## Features

### 9. How does the similar-topic checker work? Is it AI?

**Say:** "It is not machine learning; it is a transparent word-overlap measure. It turns the title and abstract into a set of words, removing punctuation, common words like 'the', and plural and -ing endings, then computes the Jaccard index: shared words divided by all words. Archived projects scoring 0.35 or more are shown as a warning. It never blocks a submission."

**Worked example:** "Campus Shuttle Delay Tracker" vs archived "Campus Shuttle Tracker": 7 shared words of 10 → 0.70 → listed.

**Limits to admit:** no synonyms ("timetable clash" vs "schedule conflict" scores 0), crude stemming, short texts swing a lot. That is why it only warns.

**Details:** `docs/explain/similarity.md`; code `apps/projects/services/similarity.py`.

### 10. What is the project health score? Is it validated?

**Say:** "A 0–100 risk score for supervisors and coordinators, from three things: days since the last held meeting, overdue milestones, and time at the current stage against the expected time. Each term is capped so no single problem dominates. The weights are heuristics I chose; they are not validated against real outcomes, and the page says so. It helps decide where to look, not to judge a student."

**Formula:** risk = 0.4·min(days since meeting / 14, 1) + 0.3·min(overdue milestones / 3, 1) + 0.3·min(days at stage / expected days, 1), × 100. Bands: under 30 on track, 30–60 watch, over 60 at risk.

**Show it:** coordinator portal → *Projects by health score* (Amina 75 at risk, each reason listed).

**Details:** `docs/explain/health-score.md`; code `apps/projects/services/health.py`.

### 11. How do the automatic reminders work, and why don't they spam people?

**Say:** "A management command, `run_automation`, checks for at-risk projects, registrations waiting over 48 hours and unacknowledged notices, and creates alerts. Every alert goes through `notify()`, which refuses a duplicate for the same person, kind and record within 24 hours, so running it every minute is safe. It needs a scheduler or a `--loop` process running; the web server does not run it."

**Details:** `docs/explain/automation.md`; code `apps/supervision/automation.py`, `services.py`.

### 12. How do the counters update without reloading the page?

**Say:** "A small script asks `/api/summary/` every 30 seconds and updates the numbers in place. It stops while the tab is hidden and on a sign-out. The endpoint returns counts only, never names, and each role sees only its own numbers."

**Details:** `docs/explain/live-counters.md`; code `api_summary` in `apps/accounts/views.py`, `static/js/live-counters.js`.

---

## Data and privacy

### 13. Is there real student data in the system?

**Say:** "No. The university cannot release student data, so the demonstration uses synthetic data created by `seed_demo`. Every demo row is flagged `is_demo`, labelled 'Sample' on screen, kept out of the audit log, and removed in one step by `purge_demo`. Real accounts are never touched by it."

### 14. Who can see what in the repository?

**Say:** "Only signed-in Baze users can browse projects; the public internet cannot. Student IDs are visible to staff only. Contact details are opt-in: each person chooses, for their personal email and for their phone number separately, whether only they, staff, or all signed-in users can see it. Private supervision records such as meeting discussions are limited to the student, their supervisor and authorised department staff."

**Details:** decisions D-09, D-14 and D-21 in `docs/decisions.md`; Q21 below.

---

## Testing

### 15. How did you test it?

**Say:** "There are more than 200 automated tests, run on both SQLite and MySQL, because MySQL behaves differently in places such as time zones, constraints and triggers. Every feature has tests for the allowed case, the forbidden case and edge cases. The layout was checked in a headless browser on every page at 360, 768 and 1280 pixels wide for horizontal scrolling."

**Show it:** `.\run_tests.ps1` from the repository root (SQLite); it prints the exact count ("Ran N tests"). Or `manage.py test apps` with MySQL configured.

---

## Admin integrity

### 16. Can an administrator change a project's stage or history directly?

**Say:** "Not through the Django admin. A project's stage, its stage dates, its archived flag and its supervisor are shown read-only there, and a project cannot be deleted there, one at a time or in bulk. The history records are view-only: no add, change or delete. A stage changes only on the workflow page, which writes the status event, the date and the audit entry together."

**Details:** `ProjectAdmin` and `ReadOnlyAdmin` in `apps/projects/admin.py`; `SupervisionMeetingAdmin` in `apps/supervision/admin.py`. Tests: `AdminCannotBypassWorkflowTests` in `apps/projects/tests_admin.py` (a hand-made POST with a new stage, dates or `archived` saves the other fields and leaves those unchanged) and `MeetingRecordAdminTests` in `apps/supervision/tests_admin.py`. Explainer: `docs/explain/admin-integrity.md`.

### 17. How do you know the audit log can't be altered?

**Say:** "Three layers. The Django admin shows audit entries read-only. The model and its queryset refuse every update and delete. And the database itself refuses UPDATE and DELETE on the audit table with triggers. Only `audit_auditevent` has triggers; no other table does. The triggers are not absolute: an account with MySQL's TRIGGER privilege can drop them, and that includes a database administrator and, with the setup in this project, the application account, which is granted all privileges on its own database."

**Details:** guards in `apps/audit/models.py`; triggers in `apps/audit/migrations/0003_append_only_triggers.py` (created on MySQL and on SQLite, so the tests exercise them); read-only admin in `apps/audit/admin.py`. The grant is in `PROGRESS.md`, "Run it on Windows", step 2. Tightening it means a separate migration account that owns the triggers and an application account without the TRIGGER privilege.

**Be ready for:** "Could you stop the app account dropping the triggers?" — Yes: run migrations with a separate account that owns the triggers, and give the application account no TRIGGER privilege. That is not done yet; it is listed in `docs/known_limits.md`.

### 18. Which records are protected, and how?

**Say:** "Every record the workflow writes is view-only in the Django admin. The history tables also refuse changes in the model, and the audit log in the database too."

**Details:**

| Records | Protection |
|---|---|
| Audit events | Database triggers on `audit_auditevent` + model and queryset guard + read-only admin |
| Project status events, approval decisions | Model and queryset guards (`PermissionError` on update or delete) + read-only admin |
| Supervisor assignments | Changed only through the audited assignment workflow + read-only admin. No model guard |
| Approval forms, completions, meeting records and their versions | Read-only admin; changed only through the workflow and meeting pages. Meeting versions (`MeetingRecordEdit`) have no admin screen of their own; they appear view-only on the meeting record |

Guards: `apps/audit/models.py`, `apps/projects/models/project.py`, `apps/projects/models/approval.py`. Admin: `apps/projects/admin.py`, `apps/supervision/admin.py`, `apps/audit/admin.py`.

### 19. What are the known limits of this protection?

**Say:** "Three that I know of. Milestones and project documents can still be edited in the Django admin. Deleting a student outside the admin, from the shell or in code, deletes their projects and every record on them. And on MySQL without its time zone tables loaded, one admin page, the meeting list, fails."

**Details:**
- **Milestones and documents:** editable as inlines on a project and on the *Project documents* admin screen (`ProjectMilestoneInline`, `ProjectDocumentInline`, `ProjectDocumentAdmin` in `apps/projects/admin.py`).
- **Deleting a student:** `Project.student` is `CASCADE`, so the projects and their status events, approvals, completion, assignments, meetings, milestones and documents go too. Only `PROTECT` stops it, with `ProtectedError`: when the student is the actor of an audit event (`AuditEvent.actor`) or has an archived project (`ArchivedProject.student`). The Django admin refuses the delete once the student has a project, because it would remove records the admin may not delete; a student without a project can still be deleted there.
- **MySQL time zone tables:** the admin's meeting list uses `date_hierarchy = "scheduled_for"`. With `USE_TZ` on and `TIME_ZONE = "Africa/Lagos"`, MySQL converts times with `CONVERT_TZ`, which needs the server's time zone tables; without them the page fails with *"Database returned an invalid datetime value"*. The application's own pages avoid this on purpose (`available_years` in `apps/projects/services/repository.py`). The fix is to load the time zone tables on the server or drop `date_hierarchy`.
- Listed with the other limits in `docs/known_limits.md`.

---

## Sign-in, contact details and demo data

### 20. What do students use to sign in, and what is the student ID?

**Say:** "Their Baze email, or their full student ID, for example `BU/23B/IT/7892`: Baze University, the year 23 and batch B, the department code IT, and the number. We don't issue usernames, because a university doesn't. The short number `7892` on its own is refused, because another year or department can have the same last digits, so it could open the wrong account."

**How it works:** `ProjectAuthenticationForm` in `apps/accounts/forms.py` looks the account up by Baze email, then by student ID (any case). At registration `clean_student_number` upper-cases the ID and checks it against `STUDENT_ID_REGEX` (`config/settings.py`; can be changed in `.env` if Baze's rules differ). Explainer: `docs/explain/accounts-and-contact.md`. Decision D-20.

**Show it:** sign in as `demo.adaeze` with `bu/22a/cs/4041` in small letters; then try `4041` alone and see the general error.

### 21. Who can see a person's phone number or personal email?

**Say:** "Only who the owner chooses. Everyone, students, alumni and staff, has a My details page with a personal email and a phone number, and for each one they pick 'Only me', 'Staff only' or 'All signed-in Baze users'. The default is 'Only me', and nothing is ever shown to someone who isn't signed in. People can't change their own Baze email, because it's how they sign in, but an administrator can correct it if it was entered wrongly; everything else the owner can change at any time. A personal email matters most for alumni, because their Baze email may close after they graduate."

**How it works:** fields and `ContactVisibility` on `User` (`apps/accounts/models.py`); `User.contact_for(viewer)` returns only what the viewer may see, so hidden details never reach the page; `ContactDetailsForm` refuses a Baze address as the personal email and checks the phone format. Tests: `apps/accounts/tests_contact.py`. Decision D-21, the interim answer to Q-04 until the supervisor confirms.

**Be ready for:** "Are the numbers verified?" — no; the format is checked, but no code is sent. It is listed in `docs/known_limits.md`.

### 22. Isn't a "show password" button a security risk?

**Say:** "It only changes how the field is displayed on the person's own screen; the password is still sent and stored the same way, hashed. It helps people type long passwords correctly, which matters because we ask for strong ones. The field goes back to hidden when the form is sent, and the button is labelled for screen readers."

**How it works:** `static/js/password-toggle.js` adds the eye button to every password field. Tests: `PasswordToggleTests` in `apps/accounts/tests.py`.

### 23. How do you keep demo data apart from real data?

**Say:** "Every demo row carries an `is_demo` flag, shown on screen as a 'Sample' tag rather than written into names. `purge_demo` removes all of it, including its files, in one step. Demo accounts are kept out of the audit log. On a database that holds both, a real administrator's or coordinator's counters count only real rows, while a demo account sees the demo story and the real rows, so a demonstration never inflates the real numbers."

**How it works:** `for_viewer` in `apps/accounts/views.py` applies the counter rule to the counters and the lists beside them; `seed_demo` and `purge_demo` in `apps/accounts/management/commands/`. Decision D-22. Limit: the review pages (Approval register and others) still list demo projects for real staff on a mixed database (`docs/known_limits.md`).

### 24. What happens if a CSV import of past projects has a mistake in it?

**Say:** "Nothing is saved. The importer checks every row, lists each wrong row with its line number and a plain reason, and only saves the file when every row is right, so a half-imported file can't happen. A supervisor or previous supervisor named in a row must be academic staff of that project's department, the same rule as assigning a supervisor."

**How it works:** `import_archived_projects` in `apps/projects/imports.py` runs in one transaction with a savepoint per row, so even a database error becomes a row error rather than a crash. `can_supervise_in` in `apps/projects/services/assignment.py` is the shared supervisor rule. Tests: `apps/projects/tests_import.py`. Decision D-23.

**Show it:** as the administrator, Admin tools → Import past projects from CSV, with `docs/sample_import.csv` after `seed_demo`.

### 25. A student or staff member entered the wrong details and can't change them. What does the administrator do?

**Say:** "They fix it; that's what the administrator is for. From System administration the admin opens the person, staff from the staff list and students by searching their name, email or student ID, and corrects the name, the Baze email, the student ID or the programme, or resets a forgotten password. The sign-in moves with a corrected email, the person gets a notice at the new address, and every change goes into the audit log. People still change their own personal email and phone themselves under My details."

**How it works:** `manage_staff_account` and `manage_student_account` in `apps/accounts/views.py`, with `StaffEditForm` and `StudentEditForm` in `apps/accounts/forms.py`; the checks are shared (`corrected_baze_email`, `checked_student_id`). Two limits protect the workflow: reactivating an account never bypasses registration approval, and a student's programme can't change once they have a project, because the project belongs to that programme's department. Tests: `apps/accounts/tests_student_admin.py` and `ManageStaffAccountTests`. Decisions D-25 and D-26.

**Show it:** as the administrator, System administration → Student accounts → search "Amina" → correct a detail → open the Audit log.
