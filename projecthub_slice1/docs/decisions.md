# Decision Log

**Version 0.1 · 2026-10-03**
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

## B. Proposed (not yet confirmed)

| ID | Proposal | Reason |
|---|---|---|
| P-01 | **Django** as the Python framework | Accepted as D-16; built-in login, roles, admin and migrations, and support for MySQL |
| P-02 | Models in Django are the source of truth; Workbench used to reverse-engineer the ER diagram | Prevents schema drift |
| P-03 | Working "unique feature" hypothesis: a **tamper-evident supervision record** (two-party confirmation, versioned edits, notices with acknowledgement, append-only audit) | Matches the supervisor's evidence stories in the transcript |
| P-04 | Contact details and student IDs hidden by default (IDs staff-only, contact with consent only) | Privacy |
| P-05 | Optional AI module: topic-similarity detection with a measured evaluation | Gives a measurable model result if time allows |
| P-06 | Project completion does not move a student to "graduated"; HOD sign-off only archives the project | Matches the separation of project and student status |

## C. Open questions for the supervisor

Ask these in one short meeting. Record answers here.

| ID | Question | Why it matters | Answer |
|---|---|---|---|
| Q-01 | What did you mean by features that "make it unique"? Any examples? | Defines the contribution section | |
| Q-02 | Is the project approval form signed, and does the title need to be fixed first? | Admin risk | |
| Q-03 | "Public": visible to anyone on the internet, or only logged-in Baze users? | Privacy and security design | **Answered 2026-10-05:** signed-in Baze Project Hub users only |
| Q-04 | Should student names, IDs and contact details appear in the repository? Is student consent needed? | Privacy | |
| Q-05 | Does Baze already have any project repository or supervision tool (Google Classroom, Moodle, forms)? | Gap statement | |
| Q-06 | Is MySQL/Workbench a requirement for all projects, and are there other written defence requirements? | Stack | |
| Q-07 | What is the exact approval chain in the department today (who signs, in which order)? | Workflow accuracy | |
| Q-08 | What does the department expect at the defence: a working system, a comparison, or both? | Scope and evaluation | |
| Q-09 | Can the department share an anonymised sample of the paper forms (not student data) to copy the form fields? | Form design | |
| Q-10 | Is a corrections-required step needed after the defence, and who clears it? | Lifecycle | |
| Q-11 | What did he mean by the other supervision project being "too much for now"? | Scope boundary | |

## D. Superseded decisions

None yet.
