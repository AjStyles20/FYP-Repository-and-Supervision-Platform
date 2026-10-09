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

### 3. How do you stop a user opening pages for another role?

**Say:** "Every non-public view is protected on the server by a `role_required` decorator: deny by default, 403 for the wrong role, the login page for anyone signed out. Hiding a menu link is never the protection."

**How it works:** `role_required(*roles)` in `apps/accounts/permissions.py` wraps `login_required` and checks `request.user.role`. Object-level checks go further: a supervisor can only open workflows for projects they supervise, a coordinator only their department's (`project_workflow` in `apps/projects/views.py`). File downloads return 404, not 403, for files outside your department, so an ID does not even confirm a file exists (`download_project_document`).

**Show it:** sign in as a student and type `/admin-tools/` in the address bar → 403 page.

### 4. Can an administrator lock everyone out?

**Say:** "No. You cannot deactivate or demote yourself, and the last active administrator cannot be deactivated or demoted by anyone. If all else fails, `createsuperuser` and `changepassword` on the server always work."

**How it works:** `StaffEditForm.clean()` and `manage_staff_account` (`apps/accounts/forms.py`, `views.py`) use `active_admin_count()`. Tests: `test_an_admin_cannot_lock_themselves_out`, `test_the_last_active_admin_cannot_be_removed_by_another_admin`.

### 5. What happens when a staff member leaves?

**Say:** "The administrator deactivates the account. They can no longer sign in, any open session ends on their next click, and nothing is deleted: their projects, meetings and audit history stay. The page warns if they still supervise active projects so those can be reassigned first."

**How it works:** `is_active=False`; Django's authentication backend refuses inactive users on every request. Test: `test_deactivation_ends_an_open_session`.

---

## Records you can trust

### 6. How do you know nobody edited the history?

**Say:** "History tables are append-only. Project status changes, approval decisions and supervisor assignments cannot be edited or deleted through the application, and the audit log is additionally protected inside MySQL by database triggers, so even direct SQL from the app account is refused."

**How it works:**
- Model and QuerySet guards raise `PermissionError` on update/delete (`apps/projects/models/project.py`, `approval.py`, `apps/audit/models.py`).
- MySQL triggers on `audit_auditevent` (`apps/audit/migrations/0003_append_only_triggers.py`) block UPDATE and DELETE at the database level.
- Meeting records keep every edit as a version (`MeetingRecordEdit`) and both student and supervisor confirm or dispute them.
- Django admin shows these tables read-only.

**Show it:** a workflow page's *Approval decisions* list (Adaeze's declined then accepted proposal) and the Audit log.

**Be ready for:** "Is anything not protected?" — Django admin can still change a project's stage directly without a status event (documented in `docs/review/02-admin-and-ui-questions.md`, question 6); in production only the administrator has Django admin access.

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

**Say:** "Only signed-in Baze users can browse projects; the public internet cannot. Student IDs are visible to staff only, a student's contact details appear only if they consented, and private supervision records such as meeting discussions are limited to the student, their supervisor and authorised department staff."

**Details:** decisions D-09, D-14 in `projecthub_slice1/docs/decisions.md`.

---

## Testing

### 15. How did you test it?

**Say:** "There are 158 automated tests, run on both SQLite and MySQL, because MySQL behaves differently in places such as time zones, constraints and triggers. Every feature has tests for the allowed case, the forbidden case and edge cases. The layout was checked in a headless browser on every page at 360, 768 and 1280 pixels wide for horizontal scrolling."

**Show it:** `.\run_tests.ps1` from the repository root (SQLite), or `manage.py test apps` with MySQL configured.
