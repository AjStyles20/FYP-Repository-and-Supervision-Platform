# Task Breakdown

**Version 0.1 · 2026-10-03**

**Legend:** `[x]` done · `[~]` in progress · `[ ]` not started · `[?]` needs an answer or verification · `[!]` risk

Requirement IDs (R-xx, N-xx) refer to `requirements.md`. Question IDs (Q-xx) refer to `decisions.md`.

---

## Phase 0 — Confirm (do this first)

- [x] Choose the project direction (FYP repository + supervision platform)
- [x] Get the supervisor's verbal go-ahead
- [x] Decide: HOD alone signs off and archives
- [x] Decide: demo data now, real data loaded by the school later
- [ ] `[!]` Get the project approval form signed
- [ ] `[?]` Ask the supervisor the open questions Q-01 to Q-11
- [ ] `[?]` Find out the final submission and defence dates and fit Phase 1–7 to them
- [ ] Choose the final project title
- [ ] Confirm the stack with the supervisor: Django + MySQL + HTML templates (P-01)

## Phase A — Problem evidence and prior art

- [ ] Write down the current paper process step by step (proposal, supervisor acceptance, form, recording, defence)
- [ ] Collect 3 to 5 real incidents (disputed submissions, missed meetings, unannounced venue changes) with dates removed or anonymised
- [ ] Check what Baze already has: Google Classroom, Moodle, forms, any archive (Q-05)
- [ ] Look at 3 to 5 comparable systems (university project repositories; supervision or appointment tools) and note what each does and does not do
- [ ] Write the gap paragraph (one paragraph, evidence-based)
- [ ] Confirm student-name/contact consent rules with the supervisor (Q-04)

## Phase B — Requirements and design

- [ ] Review `requirements.md` with the supervisor; mark accepted / rejected / deferred
- [ ] Use-case diagram (five actors)
- [ ] Activity diagram: proposal → archive
- [ ] Activity diagram: meeting request → record → confirmation
- [ ] Sequence diagram: HOD sign-off and automatic archive
- [ ] State diagram for project status
- [ ] Access-control matrix (start from `implementation_plan.md` §4)
- [ ] Page map and wireframes (start from the agreed project workflow)
- [ ] ER diagram (start from `database_schema.sql`; refine in Workbench)

## Phase C — Foundation

- [ ] Install Python 3.14, MySQL 8.4, Workbench; create the virtual environment
- [ ] Create the Django project and the apps (accounts, academics, projects, supervision, audit)
- [ ] Connect to MySQL; load credentials from environment variables
- [ ] Custom user model with role field
- [ ] Login, logout, password change; role-based redirects
- [ ] Faculty / Department / Programme models and admin screens
- [ ] `seed_demo` and `purge_demo` management commands (`is_demo = 1`)
- [ ] Base HTML template, navigation by role, simple responsive CSS
- [ ] Permission helper functions used by every view (deny by default)
- [ ] Automated tests for login and role redirects

## Phase D — Repository (R-01 to R-10)

- [x] Project, document and status-history models
- [x] Past / Current tabs; Faculty → Department → Programme filters (R-01, R-02)
- [x] Project detail page with the past-project fields (R-03)
- [x] Staff-only student ID; contact details opt-in per detail, edited by their owner under My details (R-04, R-05, D-21)
- [x] Baze student ID format and sign-in with Baze email or full student ID (D-20)
- [x] Show/hide (eye) button on password fields
- [x] Search by topic, supervisor, student name and staff-only student ID (R-06)
- [x] File upload and permission-checked download (R-07)
- [x] CSV import with a rejected-rows report; purge demo (R-10)
- [ ] Tests: visibility rules, search results, file access

## Phase E — Workflow and approval (R-11 to R-20)

- [x] Self-service approval policy per supervisor profile and snapshot on decision (R-13)
- [x] Digital approval form and evidence requirements based on the supervisor's method (R-14)
- [x] Student project start and role-checked status transitions with event history (R-11, R-12, R-17)
- [x] Coordinator screen: assign and change supervisors with history (R-18)
- [x] Supervisor counters and history page (R-19, R-20)
- [x] HOD sign-off: capture gap, archive, appear in past students (R-15)
- [x] Separate student status from project status (R-16)
- [ ] Tests: every allowed transition, every refused transition, supervisor change, single current supervisor

## Phase F — Supervision (R-21 to R-29)

- [x] Availability slots and meeting requests (R-21)
- [x] Meeting scheduling with date, time, venue (R-22)
- [x] Meeting record form and held/missed counts (R-23, R-24)
- [x] Student confirm / dispute (R-26)
- [x] Versioned meeting edits with visible history (R-27)
- [x] Notices with first-seen and acknowledged timestamps (R-25, R-28)
- [ ] Project guide page and PDF downloads (R-34)
- [ ] At-risk flag (R-29), if time allows
- [ ] Tests: confirmation flow, edit history, notice acknowledgement, record visibility (R-33)

## Phase G — Audit, security, hardening

- [x] Audit log writes for key workflow and supervision actions (R-31)
- [ ] Remove UPDATE and DELETE privilege on audit rows for the MySQL application user; add/review database guards
- [x] Admin-only audit screen with action filters
- [ ] Test that the application account cannot change audit rows
- [ ] Review: CSRF, input validation, upload limits, file serving, secure cookies
- [ ] Review: no secrets in the repository
- [ ] Back up the database and media; do one test restore
- [ ] Usability test with a few students and one or two lecturers; record results

## Phase H — Optional AI module (only after Phase G)

- [ ] Create a labelled set of project pairs (similar / not similar); second person labels a sample
- [ ] Baseline: TF-IDF + cosine similarity
- [ ] Embedding version; compare with the baseline
- [ ] Report precision at 3 and recall
- [ ] Add the "similar projects" panel to the proposal form

## Phase I — Report and defence

- [ ] Problem statement, aim, objectives, scope
- [ ] Literature / prior-art review and gap statement
- [ ] Requirements, design diagrams, ER diagram (export from Workbench)
- [ ] Implementation chapter with screenshots
- [ ] Testing chapter with permission, workflow and usability results
- [ ] Honest limitations and future work
- [ ] Demo script (use `walkthrough.md`), seeded demo database, backup recording of the demo
- [ ] Rehearse the answer to "What is different from Moodle or Google Classroom?"

## Immediate next steps

1. Ask the supervisor the Phase 0 questions and get the form signed.
2. Review the current application workflow using `walkthrough.md`.
3. Install the tools and create the Django project (Phase C).
4. Draw the ER diagram in Workbench from `database_schema.sql`.
