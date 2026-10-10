# Review 02 — Admin portal and UI questions

Branch `repo-review` at `9a2cb97`. Review date 2026-10-08. Read-only: no code, template, migration or test was changed to write this.

## How to read this

- **VERIFIED** means I read the code at the cited line (or ran the command named). **INFERRED** means it is my reasoning from what I read.
- Paths are relative to `projecthub_slice1/` unless they start with `/` (repository root).

---

## 1. The four admin-portal counters

**What they query (VERIFIED, `apps/accounts/views.py:220-233`)**

| Counter | Query | Excludes demo? |
|---|---|---|
| `pending_count` | `User` with `role=student`, `is_demo=False`, `student_profile__registration_status=PENDING` (`:221-225`, counted at `:229`) | Yes |
| `student_count` | `User` with `role=student`, `is_active=True`, `is_demo=False` (`:230`) | Yes |
| `staff_count` | `User` with `role` in supervisor/coordinator/HOD, `is_active=True`, `is_demo=False` (`:231`) | Yes |
| `programme_count` | `Programme.objects.count()` (`:232`) | **No** |

They are shown on `templates/portals/admin.html:14-17`.

**Why they read 0 after `seed_demo` (VERIFIED + INFERRED)**

- `seed_demo` creates every user with `is_demo=True` (`apps/accounts/management/commands/seed_demo.py:256`). The three user counters filter `is_demo=False`, so on a database that holds only demo data they are 0. That is intended: the counters describe real accounts only.
- The admin accounts themselves (role `admin`) are not counted by any counter.
- `programme_count` is **not** 0 after seeding: it counts all programmes, and `seed_demo` creates three (Computer Science BSc and MSc, Software Engineering BSc; `seed_demo.py:49`, `:240-242`). It is 0 only on a database with no programmes at all.
- The committed screenshot `/docs/screenshots/admin-portal-1280.png` shows 1 / 1 / 0 / 3: one real pending registration and one real student were added by the screenshot setup, there are no real staff, and the 3 programmes are the demo ones.

**Inconsistency (INFERRED):** three counters hide demo rows and one does not. If the counter should mean "real programmes", it needs `Programme.objects.filter(is_demo=False)`.

---

## 2. The CSV importer

**Where:** view `apps/projects/views.py:573-586` (admin only, `@role_required(Role.ADMIN)`), form `apps/projects/forms.py:105-114`, importer `apps/projects/imports.py:16-70`, URL `apps/projects/urls.py:19`.

**What it writes (VERIFIED)**

- One `ArchivedProject` row per good CSV row (`imports.py:55-59`), with `is_demo=False`. Table `projects_archivedproject`.
- Previous supervisors, if listed (semicolon-separated usernames), go into the many-to-many table for `ArchivedProject.previous_supervisors` (`imports.py:60-64`).
- Nothing else: no `Project`, no `ProjectStatusEvent`, no `ProjectCompletion`, no documents.

**Status:** `ArchivedProject` has no status or stage field (`apps/projects/models/archive.py:19-60`). An imported row is a finished archive record and appears in the repository's "Archived projects" list straight away (INFERRED from the model having no visibility or approval flag).

**Checks before a row is written (VERIFIED, `imports.py`)**

- The file must be `.csv`, 10 MB or smaller (`forms.py:109-113`), UTF-8 (`imports.py:18-21`), and contain all 12 headers in `CSV_COLUMNS` (`:13`, `:23-24`). If any of these fails, the whole file is rejected and nothing is written.
- Per row: title required (`:36-37`); year a number between 1900 and the current year + 5 (`:38-40`); department, programme and student must exist (`:41-43`); the student's registered programme must match (`:44-46`); the supervisor must be staff in the same department (`:48-51`); `completed_on` must be an ISO date (`:52`); no duplicate title + student + year (`:53-54`).
- At most 1,000 data rows: the import stops at row 1,002 and reports it (`:30-32`).

**Does it audit? (VERIFIED)** Yes, with one summary event per upload, not one per row: `log_event(action="repository.csv_import", details={"imported": n, "rejected_rows": m})` (`views.py:584`). It is written even when 0 rows were imported. It is not written when the whole file was rejected (`views.py:581-582`).

**What happens on a bad row (VERIFIED)**

- Each row runs in its own `transaction.atomic()` savepoint (`imports.py:34`). A bad row is rolled back by itself, including an `ArchivedProject` already created in that row if a later previous-supervisor lookup fails (`:62`).
- The error is recorded with its CSV line number (`:66-69`). The other rows carry on, and the page lists the rejected rows (`views.py:586`).
- **Gap (INFERRED):** only the listed exception types are caught (`:66-68`). A database error such as `IntegrityError`/`DataError` (for example an over-long value in a field that is not truncated) would not be caught and would give a server error for the whole request. Rows imported before it would stay, because each one committed in its own savepoint.
- **Gap (INFERRED):** previous supervisors are not checked against the project's department, unlike the main supervisor (`:61-62` vs `:50`).

---

## 3. Why "View audit log" appears several times

There are four links to the same page (`audit_log`, `/admin-tools/audit/`, `apps/accounts/urls.py:15`), not three (VERIFIED):

| Place | File and line | Link text |
|---|---|---|
| Top navigation (admin role) | `templates/base.html:50` | "Audit log" |
| Portal hero | `templates/portals/admin.html:9` | "View audit log" |
| Platform setup card | `templates/portals/admin.html:32` | "Review account and workflow audit events" |
| Admin tools page header | `templates/admin_tools.html:5` | "View audit log" |

The CSV import link is also duplicated: `admin.html:32` and `admin_tools.html:5`.

**Why (INFERRED):** all four arrived in one commit, `2af75ea` "Snapshot of uncommitted slice 2 work" (VERIFIED with `git log -S`), so there is no recorded design reason. Each page seems to have been written to stand on its own as an entry point, so each one got its own link. No code depends on the duplication. This is purely a template choice.

---

## 4. Where "(demo)" in names comes from

- **Faculty:** the name is hard-coded as `FACULTY = "Faculty of Computing (demo)"` (`seed_demo.py:46`) and created at `seed_demo.py:232`.
- **Departments and programmes are not named with "(demo)"** (`seed_demo.py:47-49`, `:235-242`: "Computer Science", "Software Engineering"). They *show* "(demo)" because `Department.__str__` appends the faculty name: `f"{self.name} ({self.faculty.name})"` (`apps/academics/models.py:38-39`). That gives "Computer Science (Faculty of Computing (demo))", which appears in dropdowns, the pending-registration card (visible in `/docs/screenshots/admin-portal-1280.png`) and anywhere else a department is printed with `{{ department }}`.
- `Programme.__str__` is `name + degree_type` (`academics/models.py:79-80`), so a programme on its own shows no "(demo)".
- All three rows already carry `is_demo=True` (`seed_demo.py:232`, `:236`, `:241`), so the suffix duplicates information the database already holds (INFERRED).

---

## 5. Which seed data sets the guide URL to example.com

- Only one place in application code: `seed_demo.py:422-426` creates a `SharedResource` titled "Literature review checklist", authored by `demo.okoro`, with `url="https://example.com/literature-checklist"`. It is linked to all of Okoro's active demo projects (`:426`). (VERIFIED, `grep -rn example.com` across the project.)
- The guide page lists shared resources (`apps/projects/views.py:554-569`) and renders `{{ resource.url }}` as an "Open guide" button (`templates/projects/guidelines.html:12`). The notices page has the same "Open link" button for the author (`templates/supervision/announcements.html:14`).
- Other `example.com` strings are in tests only (`apps/accounts/tests.py:125`, `:314`; `apps/projects/tests.py:78`, `:96`). They live in the throwaway test database and never reach a real one.

---

## 6. Django admin configuration

> **Update 2026-10-10:** fixed since this review. In the Django admin, a project's `stage`, `approval_date`, `submission_date`, `defence_date`, `archived` and `supervisor` are now read-only, and projects cannot be deleted. `ProjectApprovalForm`, `ProjectCompletion` and `SupervisionMeeting` (with its `MeetingRecordEdit` rows) joined the fully read-only list. The findings below describe the code as it was at review time; line numbers are from then. Current state: `docs/explain/admin-integrity.md`; tests: `apps/projects/tests_admin.py`, `apps/supervision/tests_admin.py`.

**Who can open `/admin/`:** any user with Django's `is_staff=True`. `seed_demo` sets this for the demo admin (`seed_demo.py:202-204`). The portal shows the "Django administration" link only to such users (`templates/portals/admin.html:32`). (VERIFIED)

**Fully read-only (no add, change or delete) (VERIFIED)**

| Model | Where |
|---|---|
| `AuditEvent` | `apps/audit/admin.py:6-20` (the model and DB triggers also block changes: `apps/audit/models.py:7-36`) |
| `ProjectSupervisorAssignment` | `apps/projects/admin.py:59-73` |
| `ProjectStatusEvent` | `apps/projects/admin.py:76-90` (model guard too: `apps/projects/models/project.py:147-193`) |
| `ProjectApprovalDecision` | `apps/projects/admin.py:93-106` (model guard: `apps/projects/models/approval.py:112-160`) |

**Partly read-only**

- `Project`: `supervisor`, `created_at`, `updated_at` are read-only (`projects/admin.py:55`). The status-event inline is read-only, cannot add and cannot delete (`:33-40`).
- Inline `AnnouncementAcknowledgement` and `MeetingRecordEdit` rows: fields read-only, no add (`apps/supervision/admin.py:15-31`). Meeting edits also cannot be deleted (`:28`).

**Fully editable:** `Faculty`, `Department`, `Programme` (`apps/academics/admin.py:5-7`); `User`, `StudentProfile`, `SupervisorProfile` (`apps/accounts/admin.py:7-20`); `ProjectDocument`, `ProjectApprovalForm`, `ProjectCompletion`, `ArchivedProject` (`projects/admin.py:43-47`, `:109-128`); `SupervisionMeeting`, `Announcement`, `SharedResource`, `SupervisionLogEntry` (`supervision/admin.py:34-70`). The supervision models have no append-only guard of their own (VERIFIED: `grep PermissionError apps/supervision` finds nothing).

**Can Projects → Change set a status without a status event? Yes at review time; no since 2026-10-10 (see the update above). (VERIFIED + INFERRED)**

- `stage` is an ordinary editable field (`apps/projects/models/project.py:72`) and is not in `readonly_fields` (`projects/admin.py:55`).
- `Project` has no `save()` override and there are no signals (`grep` for `def save`, `post_save`, `receiver` finds none for `Project`). So saving the admin form writes the new stage directly. No `ProjectStatusEvent` is created and no `log_event` runs.
- The same applies to `approval_date`, `submission_date`, `defence_date` and `archived`. Ticking `archived` in the admin does not create an `ArchivedProject` record.
- Every web-page path goes through `apps/projects/services.py` (`record_transition` and others), which writes the event. The admin is the one route around it.

---

## 7. Why the supervisor sees "Acknowledge notice" on their own notice

All VERIFIED, `apps/supervision/views.py` unless noted:

1. Staff see notices on their own projects or in their department: `Q(project__supervisor=user) | Q(department=user.department) | Q(department__isnull=True)` (`:206`). A notice the supervisor posted always matches, because it is either on their project or in their department (`:250-255`).
2. For every visible notice the view creates an acknowledgement row for the viewer and stamps `seen_at` (`:210-216`), with no check on `notice.author`. The author is therefore recorded as having "seen" their own notice.
3. The template shows the button whenever the notice requires acknowledgement and the viewer has not acknowledged it (`templates/supervision/announcements.html:18`). It does not compare the viewer with `notice.author`.
4. The POST handler accepts the acknowledgement from the author too (`:260-268`) and writes an audit event (`:268`) unless the notice is demo data.

**Fix shape (INFERRED):** skip the author when building the cards (or pass a flag the template checks), and reject an author's acknowledgement in the POST handler. Only supervisors can post notices (`can_post`, `:218`), so the author check is the whole fix.
