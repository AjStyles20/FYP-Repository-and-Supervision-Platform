# Feature comparison: what a final-year project management system is expected to do

The features a final-year project (final-year project) management system is usually expected to have, and how Baze Project Hub covers each one. Use it for the report's requirements and comparison sections, and to agree the remaining gaps with the supervisor (`docs/decisions.md`, section C).

**Legend:** ✔ built · ◐ partly built · ✘ not built. Last checked 2026-10-12.

## 1. Accounts and roles

| Feature | Status | In this system |
|---|---|---|
| Roles (student, supervisor, coordinator, Head of Department, administrator) with permission checks | ✔ | Every page is checked on the server, not by hiding links |
| Controlled student onboarding | ✔ | The coordinator (any programme of their faculty) or the administrator adds each student (D-28) |
| Fixing account mistakes | ✔ | The administrator corrects names, Baze email, student identification number and programme, and resets passwords (D-25, D-26) |
| Profiles and contact details | ✔ | My details: personal email and phone, each with its own visibility (D-21) |

## 2. Topics and approval

| Feature | Status | In this system |
|---|---|---|
| Student proposes a topic | ✔ | Proposal form on the project workflow |
| Approval workflow (supervisor → coordinator → Head of Department) | ✔ | Every decision kept in an append-only history |
| Supervisor-specific approval criteria | ✔ | Topic only, literature review, or working demonstration |
| Duplicate / similar-topic check | ✔ | Word-overlap checker against the archive |
| Topic bank (supervisors post topics, students choose) | ✘ | Not built |

## 3. Supervision

| Feature | Status | In this system |
|---|---|---|
| Supervisor allocation with even workloads | ✔ | Students waiting for a supervisor; supervisors listed least busy first (D-27, D-29) |
| Student preferences for a supervisor | ✘ | Students ask the coordinator in person |
| Supervisor change with reason and history | ✔ | A reason is required; every change is audited |
| Meeting records / logbook | ✔ | Student confirms or disputes; edits keep versions |
| Supervisor availability and meeting booking | ✔ | Students request a slot; the supervisor accepts or declines with a reason (D-32) |
| Progress / at-risk tracking | ✔ | Health score and automatic at-risk alerts |

## 4. Submissions, deadlines and feedback

| Feature | Status | In this system |
|---|---|---|
| Document upload (proposal, final report) | ✔ | Permission-checked downloads |
| Screenshots and demo videos | ✔ | Images, uploaded videos or video links (D-30) |
| Deadlines for the whole cohort (for example "Chapter 1 due 15 March") | ✔ | Faculty deadlines become milestones on every project; reminders three days before (D-33) |
| Per-student milestones | ✔ | The supervisor adds them and marks them done |
| Supervisor feedback on a submission (comments on a chapter) | ✘ | Only through meeting records |
| Plagiarism check (for example Turnitin) | ✘ | Usually a separate university system |

## 5. Defence and assessment

| Feature | Status | In this system |
|---|---|---|
| Recording the defence outcome | ✔ | Recorded by the coordinator |
| Defence scheduling (dates, rooms, panels) | ✘ | Not built |
| Marking and grading (rubrics, examiner scores, final grade) | ✘ | Not built |
| Corrections after the defence | ✘ | Known limit; depends on Q-10 |
| Head of Department sign-off and archive | ✔ | Moves files and media into the archive |

## 6. Communication

| Feature | Status | In this system |
|---|---|---|
| Notices with acknowledgement | ✔ | First-seen and acknowledged times per reader |
| In-app alerts and reminders | ✔ | Automatic alerts, live counters |
| Email notifications | ✔ | Every alert is also emailed to the Baze email (D-31) |

## 7. Repository, records and reports

| Feature | Status | In this system |
|---|---|---|
| Searchable archive of past projects, with documented gaps | ✔ | Public summaries for visitors (D-42); files and running topics need a login |
| Import of historic projects | ✔ | All-or-nothing CSV import (D-23) |
| Audit trail | ✔ | Append-only, protected by database triggers |
| Reports and exports | ✔ | Project list CSV (coordinator, Head of Department, administrator) and the convocation list CSV |

## Remaining gaps to agree with the supervisor

1. **Assessment and grading**: many departments keep marks on paper or in another system (Q-08).
2. **Defence scheduling**: dates, rooms and panel members.
3. **Supervisor feedback on submissions**: comments on a chapter.
4. **Corrections after the defence** (Q-10).
5. **Topic bank** and **student supervisor preferences**.

## Strengths compared with typical systems

- Tamper-evident records: append-only audit log, versioned meeting records, two-party confirmation.
- Similar-topic checker against the archive, and documented gaps that later students can continue.
- Project health score with reasons, and automatic reminders.
- Controlled onboarding, and an administrator who can fix any account mistake.
