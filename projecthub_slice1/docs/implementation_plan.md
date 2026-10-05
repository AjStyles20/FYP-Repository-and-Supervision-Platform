# Implementation Plan

**Version 0.1 · 2026-10-03 · Companion to `requirements.md` and `decisions.md`**

---

## 1. Scope

**In scope (MVP):** login and roles; pilot academic structure for the author's faculty/department, extensible to all Baze; authenticated-user project repository (past and current) with search and filters; supervisor assignment; configurable approval; the status workflow with HOD archive; meetings and supervision records with attendance counts; notices; availability; versioned edits; admin-only audit log; demo seeding and CSV import.

**Optional (only after the MVP works):** topic-similarity module, at-risk flag, email/SMS notifications.

**Out of scope:** LMS, timetable management, examinations, finance, general HR, student academic records.

## 2. Fixed constraints and working assumptions

Fixed (see `decisions.md`): Python + HTML web app, MySQL, no real student data, no novelty requirement, per-supervisor approval, HOD-only archive.

Decided: "public" repository browsing means authenticated Baze Project Hub users only (D-09). Still to verify: the exact approval chain at Baze (Q-07), the list of faculties/departments/programmes, and per-file publication rules. Unconfirmed academic policies must be data or configurable rules, not hard-coded.

## 3. Architecture

```text
Browser
   │  HTTPS
   ▼
Django application (single deployable)
   ├─ accounts     login, roles, permissions
   ├─ academics    faculty / department / programme
   ├─ projects     projects, status history, approvals, documents, repository search
   ├─ supervision  assignments, approval policies, meetings, records, availability, notices
   └─ audit        append-only audit log
   │
   ├──► MySQL 8 (InnoDB, utf8mb4)
   └──► File storage on disk (permission-checked downloads only)
```

Server-rendered HTML templates, plain CSS, minimal JavaScript. No separate API is needed for the MVP; add one only if a mobile app is later required.

## 4. Roles and permissions

| Capability | Student | Supervisor | Coordinator | HOD | Admin |
|---|:-:|:-:|:-:|:-:|:-:|
| Browse repository (past/current) | ✔ | ✔ | ✔ | ✔ | ✔ |
| See student ID | ✘ | ✔ | ✔ | ✔ | ✔ |
| See student contact | only with consent | only with consent | only with consent | only with consent | ✔ |
| Propose project | ✔ (own) | ✘ | ✘ | ✘ | ✘ |
| Accept idea / mark work started | ✘ | ✔ (own students) | ✘ | ✘ | ✘ |
| Record approval / defence outcome | ✘ | ✘ | ✔ | ✘ | ✘ |
| Assign or change supervisor | ✘ | ✘ | ✔ | ✘ | ✘ |
| Sign off and archive | ✘ | ✘ | ✘ | ✔ | ✘ |
| Submit final project | ✔ (own) | ✘ | ✘ | ✘ | ✘ |
| Log meeting / post notice | ✘ | ✔ | ✘ | ✘ | ✘ |
| View own meeting records | ✔ | ✔ | ✔ | ✔ | ✔ |
| Edit own entry (versioned) | ✔ | ✔ | ✔ | ✔ | ✔ |
| View audit log | ✘ | ✘ | ✘ | ✘ | ✔ |
| Manage demo data / CSV import | ✘ | ✘ | ✘ | ✘ | ✔ |

Rules are enforced in views and queries, then tested (see section 12).

## 5. Project workflow

| From → To | Who | Evidence recorded |
|---|---|---|
| (new) → Proposed | Student | Proposal text, optional "continues" link |
| Proposed → Supervisor accepted | Supervisor | Digital approval form, supervisor's approval method |
| Supervisor accepted → Approved | Coordinator | Record entry, date |
| Approved → In progress | Supervisor | Date |
| In progress → Submitted | Student | Final documents |
| Submitted → Defended | Coordinator | Outcome, date |
| Defended → Corrections required → Submitted | Coordinator / Student | Correction list |
| Defended → Completed → Archived | **HOD only** | Sign-off, documented gap |

Every transition writes a row to `project_status_history`, a row to `project_approvals` where applicable, and an `audit_log` entry. Revisions and rejections are also stored; nothing is overwritten.

## 6. Configurable approval

Each supervisor chooses a method, stored in `approval_policies`:

- `topic_only`: the supervisor hears the topic, aim and methodology and decides.
- `literature_review`: a literature review and gap analysis are needed first.
- `working_project`: the supervisor wants to see the working project first.

The method sets which checklist the digital approval form shows and is copied into the approval record at the time of decision, so later policy changes do not rewrite history. If the department later fixes a rule, it becomes an additional constraint on top of this setting.

## 7. Evidence and accountability design (working contribution hypothesis)

This answers the disputes in the supervisor's own stories: students claiming they submitted or attended, and a venue change that the supervisor could only prove from a classroom screen.

1. **Timestamped submissions.** Every upload is stored with a server timestamp and a hash of the file.
2. **Two-party meeting records.** A meeting record is created by the supervisor; the student confirms or disputes it. Both timestamps are kept.
3. **Versioned edits.** Editing a record adds a version row; earlier text is visible to the people allowed to see the record and to admins.
4. **Notice acknowledgement.** Venue or time changes are posted as notices; the system stores when each student first saw and acknowledged them.
5. **Append-only audit log.** The application database user has no UPDATE or DELETE privilege on `audit_log`, and triggers block both. This was tested on MariaDB 10.11; re-test on MySQL 8.
6. **Honest limit.** A digital log does not prove that something really happened; it proves what each party recorded and when. State this at the defence.

Mark this section as a **hypothesis until the supervisor answers Q-01**.

## 8. Repository and search

- MySQL `FULLTEXT` index on title, description and gap; filters by faculty, department, programme and year.
- Staff roles can also search by student ID. Supervisor search lists that supervisor's past and current students.
- Current projects are searchable too (D-09) so duplicate topics are visible early.
- Visibility is set per project and per file (`private`, `staff`, `baze_users`).
- The repository shows contact details only where `contact_consent = 1`.

### Optional: topic-similarity module

Goal: when a student types a proposal, show related existing projects.

1. **Baseline:** TF-IDF + cosine similarity in Python.
2. **Improvement:** sentence embeddings, compared with the baseline.
3. **Data:** create a labelled set of project pairs (similar / not similar) yourself, with a second person labelling a sample to check agreement.
4. **Evaluation:** precision at 3 and recall, baseline vs embeddings, on held-out pairs.
5. **Storage:** embeddings kept as arrays in a column and compared in Python (no vector database needed at this size).

Build this only after the MVP is stable.

## 9. Privacy and security

- Role-based access on the server; deny by default.
- Django password hashing; session cookies set secure; CSRF on every form.
- File uploads: allowed types and size limits, random file names on disk, served only through permission-checked views, never from a public folder.
- Student IDs and contact details minimised and role-restricted (R-04, R-05). Check Baze policy and the Nigeria Data Protection Act 2023 with the supervisor (Q-04).
- Secrets in environment variables; `.env` excluded from source control.
- Backups: scheduled database dump plus the media folder; test a restore once.

## 10. Demo data and handover

- `seed_demo` management command creates a faculty, departments, programmes, users, projects, meetings and notices, all with `is_demo = 1`.
- `purge_demo` removes every demo row (child tables first).
- CSV import for real past projects, validated row by row with a report of rejected rows.
- Handover note: the school removes demo data and imports its own records.

## 11. Delivery stages

Dates depend on the author's deadline. Fit the stages to the calendar once the final submission date is known.

| Stage | Goal | Exit criteria |
|---|---|---|
| S0 Confirm | Answer the open questions; get the form signed | `decisions.md` section C answered |
| S1 Design | Use cases, ER diagram, access matrix, page map | Supervisor has seen the ER diagram and screens |
| S2 Foundation | Project skeleton, MySQL connection, login, roles, academic structure | Login works for each role; permission tests pass |
| S3 Repository | Projects, search, filters, documents, demo seed | Search returns correct results; visibility rules tested |
| S4 Workflow | Assignment, approval policy, status workflow, HOD archive | Full proposal-to-archive path works end to end |
| S5 Supervision | Meetings, records, attendance counts, notices, availability, versioning | Two-party confirmation and edit history work |
| S6 Hardening | Audit log, security tests, usability tests, backups | No failing permission tests; one restore tested |
| S7 Evidence | Report, diagrams, evaluation results, demo script | Defence pack complete |
| S8 (optional) | Similarity module and at-risk flag | Evaluation numbers reported |

## 12. Testing

- **Permissions:** for each role and each action in section 4, an automated test for allowed and for denied.
- **Workflow:** every allowed transition works; every disallowed one is rejected; history rows are created.
- **Supervisor change:** old assignment preserved; only one current supervisor (database constraint).
- **Audit:** the application account cannot update or delete audit rows.
- **Search:** a fixed set of queries with expected results.
- **Privacy:** a student cannot see student IDs or unconsented contact details; unauthenticated users see nothing.
- **Usability:** short task-based test with a few students and one or two lecturers; record task success and time.
- **Evaluation (if the similarity module is built):** precision at 3 and recall against the labelled pairs.

## 13. Contribution and evaluation (for the report)

- **Problem evidence:** the supervisor's examples (disputed submission and attendance, an unannounced venue change), plus the author's own account of the paper process.
- **Existing systems:** record what Baze uses today and what comparable university repositories and supervision tools do (see `task.md`, Phase A). State the remaining gap in one paragraph.
- **Claim:** one structured system links a searchable project archive to a verifiable supervision record, with per-supervisor approval.
- **Evidence:** scenario tests that reproduce the disputed cases and show what the system can prove; usability results; permission test results.
- **Limits:** a log records claims, not truth; real adoption needs university policy; demo data only.

## 14. Risks

| Risk | Effect | Response |
|---|---|---|
| Scope grows into an ERP | Misses deadline | Scope rules in section 1; any new feature needs a requirement ID |
| Unclear contribution | Weak defence | Settle Q-01 early; keep section 7 as the working claim |
| Privacy objections | Feature removed late | Repository audience is set to authenticated Baze users (D-09); confirm name/contact consent and file-publication rules with the supervisor |
| Approval rules differ from assumptions | Rework | Approval method and chain stored as data |
| Schema drift between Workbench and Django | Broken migrations | Django models only; Workbench read-only |
| Deployment unavailable | Cannot demo live | Prepare a local demo with seeded data and a recorded backup demo |
| Approval form never signed | Admin trouble | Resolve at S0 |

## 15. Definition of done

- Every MUST requirement works and has a test.
- Permissions pass for all five roles.
- A project can go from proposal to HOD archive with history kept at each step.
- Supervision records support confirmation, dispute and edit history.
- Demo data can be removed and real data imported.
- The report states the problem, the gap, the claim, the evaluation and the limits honestly.
