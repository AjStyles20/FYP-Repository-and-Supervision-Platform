# Requirements

**Version 0.1 · 2026-10-03**

**Source codes**
- **T** = supervisor meeting transcript (timestamps in brackets). The audio is not available and the transcript is noisy, so wording is partly inferred.
- **U** = stated directly by the author (Aj).
- **P** = proposed by the assistant; needs confirmation.

**Priority:** MUST (core), SHOULD (planned), COULD (bonus, only if time allows)

---

## 1. Actors

| Actor | Description |
|---|---|
| Student | Proposes a project, meets the supervisor, submits work |
| Supervisor | Accepts ideas, supervises, logs meetings, posts notices |
| Coordinator | Assigns students to supervisors, records approvals and defence outcomes |
| Head of Department | Final sign-off; archives the project into the repository |
| Admin | Manages accounts, academic structure, demo data and imports |

## 2. Functional requirements

### 2.1 Repository

| Number | Requirement | Source | Priority |
|---|---|---|---|
| R-01 | Two sections: **past students** and **current students**; both searchable by authenticated Baze Project Hub users so topics are not repeated | U | MUST |
| R-02 | Organise by Faculty → Department → Programme; filters at each level | U | MUST |
| R-03 | Past project record shows: title, description, submission date, faculty/department/programme, student name, verified graduation year when available, final supervisor, earlier supervisor (if the student changed), documented gap, downloadable documents | U | MUST |
| R-04 | Student identification number is visible to staff roles only | U/P | MUST |
| R-05 | Contact details (personal email, phone) are each person's own and editable by them; each is shown only to the audience its owner chose (only me (the default), staff only, all signed-in Baze users, or, for the personal email only, anyone including visitors). Revised 2026-10-11 (D-21) and 2026-10-15 (D-42) | U/P | MUST |
| R-06 | Search by project topic, student name or identification number (identification number for staff), and supervisor name; searching a supervisor lists all their students and projects | U | MUST |
| R-07 | Downloadable files for past projects (even partial work), with per-file visibility and permission-checked access | U | SHOULD |
| R-08 | A new proposal can link to a past project's documented gap ("continue this gap") | P | COULD |
| R-09 | When a proposal is typed, show similar existing projects (archived and current) | P | COULD |
| R-10 | Admin can bulk-import real past projects from CSV and remove all demo data in one step | U | MUST |

### 2.2 Projects and approval

| Number | Requirement | Source | Priority |
|---|---|---|---|
| R-11 | Project lifecycle: proposed → supervisor accepted → approved → in progress → submitted → defended → completed → archived (corrections-required loop allowed) | U/T | MUST |
| R-12 | Each transition has one allowed role: supervisor accepts; coordinator records approval; supervisor marks work started; student submits; coordinator records defence; **Head of Department signs off and archives** | U | MUST |
| R-13 | **Approval method is a per-supervisor setting**: topic and aim only; strong literature review and gap; or a working final project | U | MUST |
| R-14 | The supervisor fills a digital approval form that replaces the paper form; the coordinator records it | U | MUST |
| R-15 | At Head of Department sign-off the project moves automatically to the past-students section and the documented gap is captured | U | MUST |
| R-16 | Student status (current / final-year project completed / graduated) is stored separately from project status | P | SHOULD |
| R-17 | Every status change is stored with who, when and why | T | MUST |

### 2.3 Supervision

| Number | Requirement | Source | Priority |
|---|---|---|---|
| R-18 | Coordinator assigns students to supervisors; supervisor changes keep the full history | U | MUST |
| R-19 | Supervisor counters: students supervised now, approved, defended | U | MUST |
| R-20 | Supervisor history page: current and past students and their projects, searchable by authenticated Baze users subject to project visibility | U | SHOULD |
| R-21 | Supervisor publishes availability (days/times/venue); students request a meeting from it [T 8:09–9:00] | T | SHOULD |
| R-22 | Supervisor schedules meetings with date, time and venue | U | SHOULD |
| R-23 | Meeting records: attendance, what was last discussed, corrections to make, where the student is in the project [T 3:30] | U/T | MUST |
| R-24 | Attendance counts visible to both supervisor and student (how many meetings attended / held) | U | MUST |
| R-25 | Supervisor posts notices and shares resources to their students | U | SHOULD |
| R-26 | Meeting records can be confirmed or disputed by the other party | P | SHOULD |
| R-27 | Edits to records keep earlier versions with dates (like Google Classroom) [T 10:14] | T | MUST |
| R-28 | Notices record when each student first saw and acknowledged them (proves a venue or time change was communicated) [T 11:00–13:40] | T/P | SHOULD |
| R-29 | At-risk flag when an approved project has no meeting logged for 14 days | P | COULD |

### 2.4 Access, logs and guidance

| Number | Requirement | Source | Priority |
|---|---|---|---|
| R-30 | Role-based login; permissions enforced on the server | P | MUST |
| R-31 | Audit log of important actions, **visible to admins only**; cannot be edited or deleted by the application | U | MUST |
| R-32 | Students may edit their own entries (for example, a change of supervisor); every edit is versioned | U | MUST |
| R-33 | Meeting and attendance records are visible to the student and supervisor involved, and to authorized coordinator/HOD roles; records are not exposed through the general repository | U | MUST |
| R-34 | Project guide section: Final-year project process from idea to completion and downloadable guideline PDFs [T 7:30, suggested by a student] | T | SHOULD |

## 3. Non-functional requirements

| Number | Requirement | Priority |
|---|---|---|
| N-01 | Python + HTML web app on MySQL (project defence requirement) | MUST |
| N-02 | Passwords hashed; CSRF protection; input validation; uploads limited by type and size | MUST |
| N-03 | Works on a modest connection: light pages, no heavy front-end bundle | SHOULD |
| N-04 | Works on a phone-sized screen | SHOULD |
| N-05 | Privacy: follow Baze policy and the Nigeria Data Protection Act 2023; collect only needed personal data | MUST |
| N-06 | Daily database backup procedure documented | SHOULD |
| N-07 | Extensible beyond one department without redesign | MUST |
| N-08 | Demo data clearly labelled and removable | MUST |

## 4. Out of scope

Full learning management system or Moodle replacement, timetable management, examinations, finance, hostel, library, general HR, student academic-record system, email/SMS integration (later), mobile app (later).

## 5. Open points that affect requirements

See `decisions.md`, section C (questions for the supervisor).
