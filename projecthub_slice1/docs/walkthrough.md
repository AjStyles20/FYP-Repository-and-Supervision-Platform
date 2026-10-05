# Application walkthrough

This guide describes the account flow currently implemented in Django and the academic workflow the application is being built to support. It does not imply that future project actions are already available.

## Account access

1. Visitors can sign in using a Baze email address, student ID, or staff account username.
2. Current and past final-year students can submit an account registration with a Baze email address ending in `@bazeuniversity.edu.ng`, student ID, programme, and password.
3. Student registrations remain inactive until an administrator verifies the submitted details and approves the account.
4. Staff and administrator accounts are provisioned separately; public registration cannot assign those roles.
5. An administrator reviews pending student registrations from **Admin tools**. Approval activates the account; rejection keeps it inactive.
6. The local `seed_demo` command creates clearly marked development accounts. They are test fixtures and must not be treated as university users.

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

Project-stage actions, meeting records, archives, and role-specific screens are implemented as their Django features are completed. Refer to `PROGRESS.md` for the current implementation state.
