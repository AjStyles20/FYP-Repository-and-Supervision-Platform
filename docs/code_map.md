# Code map: where to change what

"To change X, open file Y, look for Z." Paths are relative to `projecthub_slice1/`. Every row was checked with `grep` against the named file. There are no line numbers, because they go stale; search the file for the name in the last column.

## Roles, accounts and access

| To change… | Open | Look for |
|---|---|---|
| The list of roles (student, supervisor, coordinator, HOD, admin) | `apps/accounts/models.py` | `class Role` |
| Which roles may open a page | `apps/accounts/permissions.py` | `def role_required` |
| The admin's "Add staff account" form | `apps/accounts/forms.py` | `class StaffAccountForm` |
| Editing, deactivating or resetting a staff account | `apps/accounts/views.py` | `def manage_staff_account` |
| How long and how random a temporary password is | `apps/accounts/forms.py` | `def generate_temporary_password` |
| The forced password change at first sign-in | `apps/accounts/middleware.py` | `class ForcePasswordChangeMiddleware` |
| The HOD appointing the FYP coordinator and allocators | `apps/accounts/views.py` | `def department_staff` |
| The student sign-up form | `apps/accounts/forms.py` | `class StudentRegistrationForm` |
| The accepted student ID format and its error message | `config/settings.py` | `STUDENT_ID_REGEX` |
| Approving or rejecting a registration | `apps/accounts/views.py` | `def review_student_registration` |
| The approval and rejection email text | `apps/accounts/views.py` | `def _email_registration_decision` |
| The registration status page and its signed link | `apps/accounts/views.py` | `def registration_status` |
| What the login page says to a pending, rejected or deactivated account | `apps/accounts/forms.py` | `def _inactive_account_message` |

## Project stages and approval

| To change… | Open | Look for |
|---|---|---|
| The stage names and their order | `apps/projects/models/project.py` | `class ProjectStage` |
| Which role may move a project from one stage to the next | `apps/projects/services/lifecycle.py` | `TRANSITION_ROLES` |
| What happens when a stage changes (event, dates, audit) | `apps/projects/services/lifecycle.py` | `def record_transition` |
| HOD sign-off, archiving and graduation | `apps/projects/services/lifecycle.py` | `def sign_off_completion` |
| What a student's proposal must contain | `apps/projects/services/approval.py` | `def submit_proposal` |
| The supervisor's accept or decline step | `apps/projects/services/approval.py` | `def record_supervisor_decision` |
| The coordinator logging the signed approval form | `apps/projects/services/approval.py` | `def log_approved_form` |
| Which action each role sees on the workflow page | `apps/projects/views.py` | `def project_workflow` |
| Assigning or changing a project's supervisor | `apps/projects/services/assignment.py` | `def assign_project_supervisor` |
| The HOD's convocation list and its CSV columns | `apps/projects/views.py` | `CONVOCATION_COLUMNS` |

## Similar topics and health score

| To change… | Open | Look for |
|---|---|---|
| How two topics are scored (Jaccard) | `apps/projects/services/similarity.py` | `def similarity` |
| The plural / -ing word stripping | `apps/projects/services/similarity.py` | `def stem` |
| Which archived projects are listed as similar | `apps/projects/services/similarity.py` | `def similar_archived_projects` |
| The similarity threshold (0.35) | `config/settings.py` | `SIMILARITY_THRESHOLD` |
| The health score formula and its reasons | `apps/projects/services/health.py` | `def health_score` |
| Health weights, bands and expected days per stage | `config/settings.py` | `HEALTH_WEIGHTS` |
| Who may see a project's health score | `apps/projects/services/health.py` | `def can_see_health` |

## Alerts, notifications and live counters

| To change… | Open | Look for |
|---|---|---|
| Which projects the automation flags as at risk | `apps/supervision/automation.py` | `def flag_at_risk_projects` |
| The `run_automation` command and its `--loop` | `apps/supervision/management/commands/run_automation.py` | `class Command` |
| The "no duplicate within 24 hours" rule | `apps/supervision/services.py` | `def notify` |
| The kinds of notification | `apps/supervision/models/notification.py` | `class NotificationKind` |
| The Alerts page (list, mark as read) | `apps/supervision/views.py` | `def notifications` |
| The unread count in the menu | `apps/supervision/context_processors.py` | `def notifications` |
| What `/api/summary/` returns to each role | `apps/accounts/views.py` | `def api_summary` |
| The admin portal counters | `apps/accounts/views.py` | `def admin_counts` |
| The 30-second polling used by every live page | `static/js/poll.js` | `ProjectHubPoll` |

## Demo data, audit and settings

| To change… | Open | Look for |
|---|---|---|
| The demo students, staff and projects | `apps/accounts/management/commands/seed_demo.py` | `PROJECTS` |
| The demo milestones and back-dated history (health bands) | `apps/accounts/management/commands/seed_demo.py` | `def _health_story` |
| Removing all demo data | `apps/accounts/management/commands/purge_demo.py` | `class Command` |
| What gets written to the audit log | `apps/audit/services.py` | `def log_event` |
| How audit entries are labelled on screen | `apps/audit/templatetags/audit_display.py` | `ACTION_LABELS` |
| Adding or renaming faculties, departments and programmes | `apps/academics/views.py` | `def manage_structure` |
| MySQL or SQLite, and the database settings | `config/settings.py` | `DB_ENGINE` |
| Where emails go (terminal or a mail server) | `config/settings.py` | `EMAIL_BACKEND` |
| The portal greeting and its hours | `apps/accounts/templatetags/greeting.py` | `def part_of_day` |
| The theme colours | `static/css/tokens.css` | `--accent` |
| The back arrow shown on inner pages | `templates/base.html` | `block back` |

## Admin integrity and the admin hub

| To change… | Open | Look for |
|---|---|---|
| Which workflow records the Django admin may only view (no add, change or delete) | `apps/projects/admin.py` | `class ReadOnlyAdmin` |
| Which project fields the Django admin cannot change (supervisor, stage, stage dates, archived) | `apps/projects/admin.py` | `class ProjectAdmin` |
| The tests proving an admin POST cannot bypass the workflow | `apps/projects/tests_admin.py` | `class AdminCannotBypassWorkflowTests` |
| The admin hub: the one list of administration tools | `templates/admin_tools.html` | `admin-tools-heading` |
| The administrator's menu links | `templates/base.html` | `System administration` |
| The admin portal's links to the hub | `templates/portals/admin.html` | `Open admin tools` |
| The tests for the hub and the admin-only audit log and CSV import | `apps/accounts/tests.py` | `def test_admin_tools_is_the_one_hub_for_the_audit_log_and_csv_import` |
| The explainer for this feature | `../docs/explain/admin-integrity.md` | `## Self-test` |
