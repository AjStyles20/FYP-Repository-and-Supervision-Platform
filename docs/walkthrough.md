# Application walkthrough

This guide describes the account flow currently implemented in Django and the academic workflow the application is being built to support. It does not imply that future project actions are already available.

## Account access

1. Visitors sign in with their Baze email address; students can also use their full student ID (like `BU/23B/IT/7892`). Demo accounts and the server-created administrator also accept a plain username.
2. Current and past final-year students can submit an account registration with a Baze email address ending in `@bazeuniversity.edu.ng`, student ID, programme, and password.
3. Student registrations remain inactive until an administrator verifies the submitted details and approves the account.
4. Staff and administrator accounts are provisioned separately; public registration cannot assign those roles.
5. An administrator reviews pending student registrations from **Admin tools**. Approval activates the account; rejection keeps it inactive.
6. Everyone keeps their own contact details under **My details**: a personal email and a phone number, each shown only to the audience they choose (only me (the default), staff only, or all signed-in Baze users). The Baze email cannot be changed there.
7. Every password field has an eye button to show or hide what was typed.
8. The local `seed_demo` command creates clearly marked development accounts (a "Sample" tag, `is_demo`). They are test fixtures and must not be treated as university users.

## Project workflow

The intended project progression is:

| Stage | Next step | Responsible role |
|---|---|---|
| Proposed | Accept or review the idea | Supervisor |
| Supervisor accepted | Record the required approval | Coordinator |
| Approved | Begin work | Student and supervisor |
| In progress | Submit final work | Student |
| Submitted | Record the defence outcome | Coordinator |
| Defended | Sign off and archive | HOD |

Students can start a project record and submit the digital proposal. The assigned supervisor records a decision, a coordinator logs accepted forms, the supervisor records work-start, the student records submission, the coordinator records defence, and the department HOD signs completion off and archives it. Each transition is restricted by role and department and appends a status event.

The student's **My project** page links to the workflow and meeting history. Assigned supervisors schedule and edit meeting records; students can confirm or dispute them. Edits retain a version row. Supervisors can publish project or department notices, with first-seen and acknowledgement times recorded per user. Administrators can review the audit log and import past project summaries from CSV; the import is all or nothing, and every wrong row is listed with its line number.

Refer to `PROGRESS.md` for implemented screens and outstanding deployment, policy and report work. The workflow still needs an interactive browser smoke pass.
