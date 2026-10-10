# Diagrams

Mermaid sources drawn from the code on branch `repo-review`. GitHub renders `.mmd` files when they are pasted into a ```` ```mermaid ```` block. To export images, run `npx @mermaid-js/mermaid-cli -i <file>.mmd -o <file>.svg`. All five files were rendered with mermaid-cli 11 without errors.

Paths are relative to `projecthub_slice1/`. Nothing in these diagrams comes from the docs alone. Where the plan (`../implementation_plan.md`) and the code differ, the diagrams follow the code.

| File | What it shows | How it was checked |
|---|---|---|
| `er.mmd` | Every model in the five project apps, with keys, foreign keys, status fields and every relation (including `on_delete`) | **Generated** by introspecting `django.apps.apps.get_models()`, not drawn by hand. Re-generate it after any model change |
| `project_states.mmd` | Project stages and who moves them | Each transition matched to code (table below) |
| `hod_signoff_sequence.mmd` | HOD sign-off and archive, step by step | Matched line by line to `apps/projects/services/lifecycle.py:94-198` and the HOD branch of `project_workflow` |
| `architecture.mmd` | Apps, services, database, file storage | `config/settings.py`, `config/urls.py`, imports between apps |
| `use_cases.mmd` | Which role can do what | Each edge matched to a view guard (table below) |

## State machine: transition by transition

| Transition | Who (code check) | Code |
|---|---|---|
| start → Proposed | the student, with an APPROVED registration | `apps/projects/views.py` `start_project` |
| Proposed → Proposed | assigned supervisor declines, then the student resubmits (the stage doesn't change) | `services/approval.py` `record_supervisor_decision` (REJECTED leaves the stage), `submit_proposal` |
| Proposed → Supervisor accepted | the assigned supervisor (role supervisor, coordinator or HOD), with the evidence the method requires | `services/approval.py` `record_supervisor_decision`; `services/lifecycle.py` `TRANSITION_ROLES`, `SUPERVISOR_TRANSITIONS` |
| Supervisor accepted → Approved | coordinator of the project's department | `services/approval.py` `log_approved_form`; `lifecycle.py` `TRANSITION_ROLES` |
| Approved → In progress | the assigned supervisor | `lifecycle.py` `SUPERVISOR_TRANSITIONS` |
| In progress → Submitted | the project's own student, only if a REPORT document exists | `lifecycle.py` `record_transition` (REPORT check) |
| Submitted → Defended | coordinator of the project's department | `lifecycle.py` `TRANSITION_ROLES`, department check |
| Defended → Completed | HOD of the project's department, with a gap summary or the "no gap" box | `lifecycle.py` `sign_off_completion` |

There are no transitions other than these (VERIFIED: `TRANSITION_ROLES` has five entries, and sign-off is the only other path to a new stage).

## Use cases: edge by edge

| Use case | Roles (view guard) | View |
|---|---|---|
| Register | visitor | `accounts/views.py` `register_student` |
| Sign in | anyone | `ProjectLoginView` + `ProjectAuthenticationForm` |
| Approve or reject a registration, audit log | admin | `review_student_registration`, `audit_log` (`role_required(ADMIN)`) |
| Search and filter | all five roles | `repository`, `running_topics` (`REPOSITORY_ROLES`) |
| Download a project file | student (own or public archived), staff of the department, assigned supervisor, admin | `download_project_document`, `_can_open_current_project_files` |
| Import from CSV | admin | `import_projects` |
| Academic structure | supervisor, coordinator, HOD, admin | `academics/views.py` `structure` |
| Start, propose, upload, submit | the project's own student | `start_project`, `project_workflow` (student branches), `upload_project_document` |
| Decide on a proposal, mark started | the assigned supervisor of any supervising role | `project_workflow` (`project.supervisor_id == user.pk`) |
| Log the approval form, record the defence | coordinator of the department | `project_workflow` (coordinator branches) |
| Sign off and archive | HOD of the department | `project_workflow` (HOD branch) |
| Status history and approval decisions | own student, assigned supervisor, coordinator or HOD of the department, admin | `project_workflow` access checks, `templates/projects/workflow.html` |
| Assign a supervisor | any staff role with `can_assign_supervisors`, own department | `supervisor_assignments` |
| Add or remove an unassigned student | role supervisor only | `supervision` (`can_manage_roster`) |
| Schedule and edit meetings | the assigned supervisor of any supervising role | `project_meetings`, `edit_meeting` (`_meeting_editor`) |
| Read meeting records | own student, assigned supervisor, coordinator or HOD of the department (R-33). **Not** admin | `_project_access` |
| Confirm or dispute a record | student (confirm or dispute), assigned supervisor (confirm) | `meeting_detail` |
| Post a notice, share a resource | role supervisor only | `announcements` (`can_post`) |
| Read and acknowledge notices, open resources | students (resources only if sent to their current project) | `announcements`, `student_resource_scope` |
| Publish availability, set approval criteria | supervisor, coordinator, HOD | `availability`, `approval_policy` |
