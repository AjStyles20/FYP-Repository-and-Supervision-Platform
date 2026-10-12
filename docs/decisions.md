# Decision Log

**Version 0.2 · 2026-10-12** (D-20 to D-24 added; interim answer to Q-04)
Update this file whenever a decision is made or an open question is answered. Never delete an old decision; mark it superseded.

---

## A. Decided (stated by the author)

| ID | Decision | Notes |
|---|---|---|
| D-01 | Project is a **FYP repository and project management/supervision platform** for Baze University | Title not final |
| D-02 | Begin with the author's own faculty and department; design for all faculties | |
| D-03 | Stack: **Python, HTML, web app, MySQL** (designed in Workbench) | Workbench is the design tool; the database is MySQL Server. Confirm the HOD requirement in Q-06 |
| D-04 | School does not require novelty | A contribution statement is still needed |
| D-05 | Student data cannot be released to students, so use **self-created demo data** that the school replaces later | Do not collect old FYPs |
| D-06 | **Approval criteria vary by supervisor**; no fixed rule | Becomes a per-supervisor setting |
| D-07 | Logs for admins only; students can edit their own entries (for example a change of supervisor) | All edits versioned |
| D-08 | **Only the HOD signs off and archives** | Confirmed 2026-10-03 |
| D-09 | Past and current project sections are visible to authenticated Baze Project Hub users to prevent repeated and copied topics; they are not open to unauthenticated internet visitors | User clarified 2026-10-05; student IDs remain staff-only and contact is opt-in |
| D-10 | Supervisor said to go ahead with implementation; he said more features will be added later | Approval form unsigned |
| D-11 | The gap/continue and similar-topic features are **not** what the supervisor meant by "unique features" | Kept only as bonus modules |
| D-12 | The author wants to build this one and enjoys AI model work and building a polished product | Shapes the optional AI module |
| D-13 | First launch focuses on the author's faculty and department, while the data/navigation structure supports all Baze faculties, departments, programmes and awards | User's initial product direction |
| D-14 | General project discovery and private supervision evidence are separate: meeting discussion/corrective-action records are limited to the student, assigned supervisor and authorized academic staff | Privacy-preserving interpretation of accountability requirement; confirm departmental policy |
| D-15 | HOD sign-off of FYP completion automatically archives the project; graduation status/year is separately verified and recorded by the HOD | User clarified 2026-10-05; do not infer graduation from project completion |
| D-16 | The existing Django application is the authoritative product foundation; consolidate the project work into it and build the real Baze system there | User clarified 2026-10-05 |
| D-17 | "My project" is a student-only workspace; staff supervision history lists only that staff member's current and past supervisees, linked to project summaries | User clarified 2026-10-05 |
| D-18 | Supervisor-allocation authority is granted independently from job title and scoped to the staff member's department; an eligible supervisor or HOD may also receive it | User clarified 2026-10-05; administered as an explicit staff permission |
| D-19 | The HOD does HOD work: signs off final projects when the student brings the physical final documents and keeps the convocation list. The HOD appoints the FYP coordinator and the lecturers who assign supervisors, from lecturers in their department. Only the coordinator logs approved topics and records defences; the HOD does not do the coordinator's steps. A coordinator is never the HOD | User clarified 2026-10-09; HOD queue shows final sign-off only; convocation list printable and downloadable |
| D-20 | **Student ID** is the full Baze number, `BU/<year><batch>/<department code>/<number>`, e.g. `BU/23B/IT/7892` (year 23, batch B of A, B or C, department IT, number 7892). Stored in capitals. Everyone signs in with their Baze email; students may also use the full ID. The short number alone (`7892`) is not accepted, because it can repeat across years and departments. No separate usernames are issued | User clarified 2026-10-11; the format is `STUDENT_ID_REGEX` in `.env` if Baze's rules differ |
| D-21 | **Contact details** belong to each person (students, alumni and staff): a personal email and a phone number, both editable by their owner at any time. The Baze email (the sign-in) is not self-editable; an administrator corrects it when it is wrong (D-25). Each detail has its own visibility: only me (the default), staff only, or all signed-in Baze users. Nothing is shown to people who are not signed in | User clarified 2026-10-11; a personal email keeps alumni reachable after their Baze email closes. Interim answer to Q-04 |
| D-22 | **Demo data** is marked only by `is_demo` (shown as a "Sample" tag), never by "(demo)" in names. A demo account's counters and lists count demo and real rows; a real account's count real rows only | User decided 2026-10-10 |
| D-23 | **CSV import of past projects is all or nothing:** if any row is wrong, nothing is saved and every wrong row is listed. Supervisors and previous supervisors must be academic staff of the project's department (no active check for historic records). Rows about demo students are imported as demo data | User decided 2026-10-10 |
| D-24 | The author is the system administrator for development and the demonstration | User stated 2026-10-11 |
| D-25 | An administrator can **correct a staff member's Baze email**, including their own, on the staff account page. It must be a Baze address no other account uses; the sign-in moves to the new address, the change is audited (old and new address) and a notice is sent to the new address | User decided 2026-10-12, after the demo admin email could not be changed |
| D-26 | **Fixing account mistakes is the administrator's job.** For students as for staff, an administrator can find the account, correct the name, Baze email (sign-in), student ID and programme, reset a forgotten password and deactivate or reactivate it; every change is audited. Two limits protect the workflow: reactivation never bypasses registration approval, and the programme cannot change once the student has a project. Personal email and phone stay with their owner (My details); graduation stays with the HOD (D-15) | User decided 2026-10-12 |
| D-27 | **Allocation follows the department's practice:** a student meets the coordinator, who gives them a supervisor before they choose a topic, keeping numbers even across supervisors (the coordinator may supervise them too). Allocating creates the student's project record ("Topic to be agreed"); the proposal sets the title. A student who wants a different supervisor asks the coordinator in person; the coordinator decides, and a change must give a reason, kept in the history. A coordinator allocates across their faculty (D-29) | User described 2026-10-12 |
| D-28 | **Students do not create their own accounts.** The administrator (any department) or the FYP coordinator (any programme of their faculty, D-29) adds each final-year student, with the same checks as before (Baze email, Baze student ID format, both unique). The account is active at once; a temporary password is shown once and the student chooses their own at first sign-in; the creation is audited. Public self-registration is kept in the code but switched off (`STUDENT_SELF_REGISTRATION=False`) | User decided 2026-10-12: account creation must be regulated, so only students ready for their FYP get accounts |
| D-29 | **A coordinator works across their whole faculty.** Their own department only records their teaching field (e.g. a Cyber Security lecturer coordinating the Faculty of Computing). They add students for any programme of the faculty and, on Student allocation, see the faculty's waiting students and projects and may choose any supervisor of the faculty. A supervisor or HOD given the allocation permission stays within their own department, and the HOD's own work (sign-off, department staff) stays department-scoped. Refines D-18 | User clarified 2026-10-12 |
| D-30 | **Screenshots and demo videos** on running and archived projects alike: up to 6 images (JPG, PNG, WebP; 5 MB) and 2 videos (MP4/WebM upload up to 100 MB, or a YouTube, Google Drive or Vimeo link). Same access as project files: the project's people while it runs, then the archive's visibility after sign-off. Added by the student (running) or an administrator (archived); type, size and content checked; audited. No audio, no profile photos, no general media library | User decided 2026-10-12 |

## B. Proposed (not yet confirmed)

| ID | Proposal | Reason |
|---|---|---|
| P-01 | **Django** as the Python framework | Accepted as D-16; built-in login, roles, admin and migrations, and support for MySQL |
| P-02 | Models in Django are the source of truth; Workbench used to reverse-engineer the ER diagram | Prevents schema drift |
| P-03 | Working "unique feature" hypothesis: a **tamper-evident supervision record** (two-party confirmation, versioned edits, notices with acknowledgement, append-only audit) | Matches the supervisor's evidence stories in the transcript |
| P-04 | Contact details and student IDs hidden by default (IDs staff-only, contact with consent only) | Privacy. Implemented as D-21 (opt-in per detail) |
| P-05 | Optional AI module: topic-similarity detection with a measured evaluation | Gives a measurable model result if time allows |
| P-06 | Project completion does not move a student to "graduated"; HOD sign-off only archives the project | Matches the separation of project and student status |

## C. Open questions for the supervisor

Ask these in one short meeting. Record answers here.

| ID | Question | Why it matters | Answer |
|---|---|---|---|
| Q-01 | What did you mean by features that "make it unique"? Any examples? | Defines the contribution section | |
| Q-02 | Is the project approval form signed, and does the title need to be fixed first? | Admin risk | |
| Q-03 | "Public": visible to anyone on the internet, or only logged-in Baze users? | Privacy and security design | **Answered 2026-10-05:** signed-in Baze Project Hub users only |
| Q-04 | Should student names, IDs and contact details appear in the repository? Is student consent needed? | Privacy | **Interim answer by the author 2026-10-11 (D-21):** student IDs staff-only; each contact detail opt-in, with its owner choosing who sees it. Confirm with the supervisor |
| Q-05 | Does Baze already have any project repository or supervision tool (Google Classroom, Moodle, forms)? | Gap statement | |
| Q-06 | Is MySQL/Workbench a requirement for all projects, and are there other written defence requirements? | Stack | |
| Q-07 | What is the exact approval chain in the department today (who signs, in which order)? | Workflow accuracy | |
| Q-08 | What does the department expect at the defence: a working system, a comparison, or both? | Scope and evaluation | |
| Q-09 | Can the department share an anonymised sample of the paper forms (not student data) to copy the form fields? | Form design | |
| Q-10 | Is a corrections-required step needed after the defence, and who clears it? | Lifecycle | |
| Q-11 | What did he mean by the other supervision project being "too much for now"? | Scope boundary | |

## D. Superseded decisions

None yet.
