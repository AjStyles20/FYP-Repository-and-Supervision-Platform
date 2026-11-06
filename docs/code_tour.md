# Code tour: ten flows to explain at the defence

For a student explaining code they did not write line by line. Paths are relative to `projecthub_slice1/`. Every reference was checked against the code on 2026-10-13; line numbers move when code changes, so search for the name if a line looks wrong. **Differs from the brief** marks where the code does something other than expected. **Unverified** marks what was not confirmed.

## 1. Login by Baze email (student identification number no longer signs in)
- **Web address:** `login` (`apps/accounts/urls.py:8`)
- **View:** `ProjectLoginView` (`apps/accounts/views.py:76`): Django's `LoginView` with a custom form
- **Logic:** no service; it is the form: `ProjectAuthenticationForm.clean` (`apps/accounts/forms.py:26`)
- **Models:** `User.email` (inherited from Django's `AbstractUser`, `apps/accounts/models.py:36`); `StudentProfile.student_number`, `unique=True` (`apps/accounts/models.py:103`)
- **Template:** `templates/registration/login.html`
- **Test:** `test_active_student_logs_in_with_the_baze_email_only` (`apps/accounts/tests.py`)

**Changed 2026-10-14 (D-41):** the form looks up the account whose email matches, ignoring case, and swaps in its username for Django's normal password check. Anything that is not an account's email (a student identification number, an internal username) becomes a blank, which matches no account, so the login fails. Line numbers in `forms.py` moved with this change; search for `ProjectAuthenticationForm`.

**Differs from the brief:** the student identification number no longer logs in. The email is not unique in the database; the code takes the `.first()` match. Uniqueness is enforced by the forms that create accounts (for example `forms.py:104`). **Unverified:** whether every other route (`createsuperuser`, the Django admin) blocks a duplicate email.

**If the panel asks:** "Does the error message reveal whether an email is registered?"
No: `_inactive_account_message` (`forms.py:48`) returns a status only when the password is correct for an inactive account (`forms.py:56`). Anyone with a wrong password gets the same generic error.

## 2. Registration and admin approval of accounts
- **Web addresses:** `register_student` (`apps/accounts/urls.py:9`), `registration_status` (`:10`), `review_student_registration` (`:25-29`), `add_student_account` (`:21`)
- **Views:** `register_student` (`apps/accounts/views.py:81`), `review_student_registration` (`views.py:658`, admin only, POST only), `add_student_account` (`views.py:507`, admin or coordinator)
- **Logic:** `StudentRegistrationForm.save` (`apps/accounts/forms.py:140`) creates the user with `is_active=False` (`forms.py:150`) and the profile as `PENDING` (`forms.py:157`)
- **Model:** `StudentProfile.registration_status`, default `APPROVED` (`apps/accounts/models.py:108`)
- **Templates:** `registration/register.html`, `registration/status.html`, `registration/closed.html`, `admin_tools.html`, `accounts/student_form.html`
- **Tests:** `test_admin_can_approve_or_reject_pending_accounts` (`apps/accounts/tests.py:545`); `test_self_registration_is_closed_by_default` (`apps/accounts/tests_add_student.py:38`)

When self-registration is on, a student's account is created inactive and pending. An administrator approves or rejects it, which changes the status, activates the account or not, audits the decision and emails the student (`views.py:673-691`). A rejection reason is stored in the audit event's details (`views.py:681-683`).

**Differs from the brief:** self-registration is **off by default** (`STUDENT_SELF_REGISTRATION`, `config/settings.py:162`; `views.py:84` shows `closed.html`). The normal route is `add_student_account`: an administrator or coordinator creates an account that is active at once, with a temporary password. Approval applies only when self-registration is switched on, and only an administrator can approve; a coordinator cannot.

**If the panel asks:** "Why does a profile default to APPROVED?"
Staff-created accounts are trusted, so only the self-registration form overrides the default with `PENDING` (`forms.py:157`). A pending account also has `is_active=False`, so Django's login refuses it.

## 3. Proposal submission and the similar-topic check
- **Web address:** `project_workflow` (`apps/projects/urls.py:21`)
- **View:** `project_workflow` (`apps/projects/views.py:481`); the submit call is at `views.py:538`, the warning `_warn_about_similar_topics` at `views.py:54`
- **Services:** `submit_proposal` (`apps/projects/services/approval.py:56`); `jaccard` (`apps/projects/services/similarity.py:58`); `similar_archived_projects` (`similarity.py:74`)
- **Threshold:** `SIMILARITY_THRESHOLD = 0.35` (`config/settings.py:176`), fallback `DEFAULT_THRESHOLD = 0.35` (`similarity.py:17`), compared with `>=` (`similarity.py:90`)
- **Model:** `ProjectApprovalForm`: `proposed_title`, `student_signed_on` (`apps/projects/models/approval.py:24`, `:43`, `:52`)
- **Template:** `templates/projects/workflow.html` (the panel is included from `projects/_similar_projects.html`)
- **Tests:** `SimilarityScoreTests` (`apps/projects/tests.py:1107`); `test_proposal_with_a_similar_title_is_saved_with_a_warning` (`tests.py:1193`); `test_threshold_comes_from_settings` (`tests.py:1234`)

`jaccard` is the shared words divided by all words: `len(a & b) / len(a | b)`, and 0.0 when both sets are empty (`similarity.py:58-62`). Before comparing, `tokens` lowercases the text, drops stop-words and strips plural and -ing endings (`similarity.py:53-55`). Submitting saves the proposal first, then warns about any matches, so a match never blocks a submission (`views.py:538-540`).

**Differs from the brief:** the check compares the project's **title and description** (`views.py:56`), not the proposal's problem statement or objectives. `submit_proposal` updates only the project title (`approval.py:97-99`).

**If the panel asks:** "Does a score of exactly 0.35 count as similar?"
Yes: the test is `score >= threshold` (`similarity.py:90`). At most five matches are shown, best first (`MATCH_LIMIT`, `similarity.py:18`, `:92-93`).

## 4. Supervisor approval and where the approval method is stored
- **Web address:** `project_workflow` (`apps/projects/urls.py:21`); a supervisor sets their method at `approval_policy` (`apps/supervision/urls.py:14`)
- **Views:** `project_workflow` (`apps/projects/views.py:481`), decision form at `views.py:543-545`; `approval_policy` (`apps/supervision/views.py:465`)
- **Service:** `record_supervisor_decision` (`apps/projects/services/approval.py:112`)
- **Models:** `SupervisorProfile.approval_method` and `approval_criteria` (`apps/accounts/models.py:140`, `:146`); snapshot on `ProjectApprovalForm.approval_method` and `approval_criteria_snapshot` (`apps/projects/models/approval.py:26`, `:36`); each decision kept in `ProjectApprovalDecision` (`approval.py:118`, its own copy at `:143-144`)
- **Templates:** `projects/workflow.html`, `supervision/approval_policy.html`
- **Test:** `test_rejection_survives_resubmission_and_full_history_is_kept` (`apps/projects/tests.py:862`)

The method lives on the supervisor's profile, and each supervisor chooses it on the approval policy page. On a decision, the service checks that the decider is the assigned supervisor and that the proposal has been submitted. It also checks that the evidence this method requires is present (`approval.py:114-128`). It then copies the method and criteria onto the form as a snapshot, records a decision row, and moves the project to "Supervisor accepted" if accepted (`approval.py:129-155`).

**If the panel asks:** "If a supervisor changes their method later, does an old decision change?"
No: the method and criteria are copied onto the form at decision time (`approval.py:130-131`), and onto each decision row. Those rows cannot be changed or deleted (test at `tests.py:900`).

## 5. Supervisor assignment and history
- **Web address:** `supervisor_assignments` (`apps/projects/urls.py:23`)
- **View:** `supervisor_assignments` (`apps/projects/views.py:873`); reassignment calls the service at `views.py:930`, allocation at `views.py:913`
- **Service:** `assign_project_supervisor` (`apps/projects/services/assignment.py:76`)
- **Model:** `ProjectSupervisorAssignment`: `assigned_at`, `ended_at`, `change_reason`, `is_current` (`apps/projects/models/assignment.py:41`, `:58-62`); the constraint `one_current_supervisor_per_project_v2` (`:67`)
- **Template:** `templates/projects/supervisor_assignments.html`
- **Tests:** `test_reassignment_service_keeps_exactly_one_current_row` (`apps/projects/tests.py:679`); `test_second_current_supervisor_is_rejected_by_the_database` (`tests.py:629`)

The service locks the project and the open assignment row (`select_for_update`, `assignment.py:78`, `:87-91`). A change closes the old row by setting `ended_at = now` and saving it (`assignment.py:99-101`). It then opens a new row and audits the change (`assignment.py:113-122`). `save()` turns `is_current` from True to NULL once `ended_at` is set (`models/assignment.py:22-23`, `:78-83`).

**If the panel asks:** "How does the database stop two current supervisors, even on MySQL?"
Each row has `is_current`, which is True while open and NULL once ended. A plain unique rule on `(project, is_current)` allows many NULLs but only one True (`models/assignment.py:6-11`, `:67`). A check constraint keeps `is_current` in step with `ended_at` (`:68-71`).

## 6. Meeting request, accept and decline
- **Web address:** `project_meetings` (`apps/supervision/urls.py:6`)
- **View:** `project_meetings` (`apps/supervision/views.py:170`), branches `request_meeting` at `views.py:179` and `decide_request` at `views.py:184`
- **Logic:** `_request_meeting` (`views.py:99`), `_decide_meeting_request` (`views.py:131`), `_has_schedule_conflict` (`views.py:36`), `_slot_duration` (`views.py:92`)
- **Models:** `SupervisorAvailability.weekday` (`apps/supervision/models/meeting.py:33`, `:39`); `MeetingRequest`: `availability`, `requested_date`, `status`, `decision_note` (`meeting.py:70`, `:78-84`); the weekday check is in `clean` (`meeting.py:96`)
- **Template:** `templates/supervision/meetings.html`
- **Tests:** `apps/supervision/tests_booking.py:73` (accept), `:84` (decline), `:68` (busy time)

The student picks one of the supervisor's weekly windows and a date. The request is refused if the date is on a different weekday, if the same request is already pending, or if the supervisor already has a meeting then (`views.py:107-119`). Accepting creates a scheduled meeting at the window's start, for the longest standard length that fits. Declining needs a reason, and the student is alerted either way (`views.py:139-164`).

**Differs from the brief:** there is no separate service module; the logic is in private functions in `views.py`. An accepted request is stored as `APPROVED`, not "accepted" (`meeting.py:73`, `views.py:156`).

**If the panel asks:** "What if two requests for the same slot are accepted?"
Accepting checks for a clash again, and if one exists it refuses with a message (`views.py:148-150`). **Unverified:** whether two acceptances submitted at the same instant could both pass, because the request row is locked (`views.py:134`) but the supervisor's meetings are not.

## 7. Coordinator uploads the final report; the submit check
- **Web address:** `upload_project_document` (`apps/projects/urls.py:13`)
- **View:** `upload_project_document` (`apps/projects/views.py:1012`); `_coordinator_can_upload` (`views.py:47`); stages `COORDINATOR_UPLOAD_STAGES` (`views.py:44`) and `STUDENT_UPLOAD_STAGES` (`views.py:42`)
- **Service:** `record_transition` (`apps/projects/services/lifecycle.py:53`); the check at `lifecycle.py:72`
- **Model:** `ProjectDocument`: `document_type`, `visibility`, `uploaded_by` (`apps/projects/models/document.py:37`, `:51`, `:63`, `:68`)
- **Templates:** `projects/document_upload.html`, `projects/workflow.html`
- **Tests:** `apps/projects/tests_coordinator_upload.py:57`, `:79` (other department), `:96` (sign-off still archives)

A coordinator may upload for a project in their own department at the in-progress, submitted or defended stage. A project from another department returns "not found" (`views.py:1016`). The file is saved staff-only under the coordinator's name, and the upload is audited with their role (`views.py:1027-1033`). Separately, `lifecycle.py:72` refuses the move to "Submitted" unless the project has a document of type `report`, whoever uploaded it.

**Differs from the brief:** **no test checks the refusal at `lifecycle.py:72`.** The tests and the demo seed always upload a report first (for example `tests.py:314`). The check is covered only indirectly. A coordinator's upload at the in-progress stage satisfies it, so the student can then submit.

**If the panel asks:** "Does a file saved as 'Other' let the student submit?"
No: the check filters on `document_type=DocumentType.REPORT` (`lifecycle.py:72`). The coordinator's form only starts on "Final report" (`views.py:1023`), and the coordinator can change it.

## 8. Head of Department sign-off and archive
- **Web address:** `project_workflow` (`apps/projects/urls.py:21`), Head of Department branch at `apps/projects/views.py:579-582`
- **Service:** `sign_off_completion` (`apps/projects/services/lifecycle.py:95`, `@transaction.atomic` at `:94`), `_archive_project` (`:147`), `_update_student_status` (`:190`)
- **Models:** `ProjectCompletion`: `signed_on`, `gap_summary`, `no_gap_confirmed`, `graduation_verified`, `graduation_year` (`apps/projects/models/approval.py:163`, `:173-181`); `ArchivedProject`: `year`, `completed_on`, `defence_date` (`apps/projects/models/archive.py:19`, `:24-26`)
- **Form:** `CompletionForm` (`apps/projects/forms.py:178`)
- **Templates:** `projects/workflow.html`, then `projects/project_detail.html` for the archived record
- **Tests:** `CompletionGapCheckTests` (`apps/projects/tests.py:919`); `test_sign_off_keeps_the_semester_even_in_the_next_calendar_year` (`apps/projects/tests_semesters.py:149`)

Sign-off needs either a documented gap or a "no gap" tick, not both. It also needs a year whenever graduation is verified (`lifecycle.py:112-118`). Only the Head of the project's department can sign off, and only at the "Defended" stage (`:119-125`). In one transaction it creates the archived record, moves every document and media item to it, marks the project completed and sets the student to "Final-year project completed" or "Graduated" (`:151-202`).

**If the panel asks:** "Which year does the archive show for a project signed off in January?"
The sign-off date's calendar year: `year=completion.signed_on.year` (`lifecycle.py:155`). The semester is copied alongside it (`:158`), so a 26C project signed off in January 2027 shows 2027 and 26C.

## 9. Repository search and the staff-only student identification number search
- **Web addresses:** `repository` and `running_topics` (`apps/projects/urls.py:6-7`)
- **Views:** `repository` (`apps/projects/views.py:122`), `running_topics` (`views.py:132`), shared `_repository_context` (`views.py:65`), where `can_see_student_id = request.user.role in STAFF_ROLES` (`views.py:66`)
- **Service:** `_apply_search` (`apps/projects/services/repository.py:116`); the fields in `SEARCH_FIELDS` (`repository.py:15`), plus `gap_summary` for past projects (`:28`)
- **Models:** `Project` and `ArchivedProject` fields as listed; `STAFF_ROLES` (`apps/accounts/models.py:14`) includes the administrator
- **Template:** `templates/projects/repository.html`
- **Tests:** `test_student_id_search_is_not_available_to_students` (`apps/projects/tests.py:345`); `test_staff_can_search_by_student_id` (`tests.py:353`)

Search is a case-insensitive "contains" match across title, description, keywords, student, supervisor, department, faculty and programme names (`repository.py:15-27`, `:120-121`). The student identification number is added to the search only when the viewer is staff (`repository.py:122-124`). For a student, typing an identification number simply finds nothing.

**If the panel asks:** "Why `.distinct()` at the end of the search?"
The search can match through related rows, which may return the same project more than once. `.distinct()` lists each project once (`repository.py:125`).

## 10. Audit log: triggers, migration, and what could drop them
- **Web address:** `audit_log` (`apps/accounts/urls.py:17`); **view:** `audit_log` (`apps/accounts/views.py:730`, admin only)
- **Service:** `log_event` (`apps/audit/services.py:4`); it records nothing for demo actors or demo records (`:6-7`)
- **Model:** `AuditEvent` (`apps/audit/models.py:13`): `actor` PROTECT (`:16`), `action`, `object_type`, `object_id`, `summary`, `details`, `created_at` (`:17-22`). Python guards refuse `save` on an existing row, and `update` and `delete` (`:5-10`, `:30-36`)
- **Migration:** `apps/audit/migrations/0003_append_only_triggers.py`: `create_triggers` (`:22`) adds `BEFORE UPDATE` and `BEFORE DELETE` triggers on SQLite and MySQL (`:24-34`); it runs with `atomic=False` because MySQL cannot run this inside a transaction (`:50-52`)
- **Template:** `templates/audit/log.html`
- **Tests:** `test_triggers_are_installed` (`apps/audit/tests.py:73`); raw SQL refused (`:77`, `:83`)

Every audited action goes through `log_event`, which only ever inserts a row. The model refuses edits in Python, and the database triggers refuse an UPDATE or DELETE even from raw SQL. The admin reads the log at `/admin-tools/audit/`.

**Differs from the brief:** nothing in the running app drops the triggers. The only `DROP TRIGGER` in the code is `drop_triggers` (`0003_append_only_triggers.py:37-40`), the migration's reverse step. It runs only if someone rolls the audit app back with `migrate audit 0002`. Outside the code, dropping or rebuilding the table also removes them (`:7-8`). So can a MySQL account with the TRIGGER privilege (see `docs/known_limits.md`).

**If the panel asks:** "Can the administrator delete an embarrassing audit entry?"
Not through the app: the queryset and model refuse it, and the database triggers refuse even raw SQL (`models.py:9-10`, `:35-36`; tests at `tests.py:77-89`). Only someone with database rights could drop the triggers first. That is the limit to admit.
