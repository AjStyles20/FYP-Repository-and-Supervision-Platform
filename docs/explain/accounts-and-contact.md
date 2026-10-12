# Accounts and contact details

How people sign in, what a student ID looks like, how everyone keeps their own contact details, and the eye button on password fields. Decisions D-20 and D-21 in `docs/decisions.md`.

Code: `STUDENT_ID_REGEX` in `projecthub_slice1/config/settings.py`; `ProjectAuthenticationForm`, `StudentRegistrationForm.clean_student_number` and `ContactDetailsForm` in `projecthub_slice1/apps/accounts/forms.py`; `ContactVisibility` and `User.contact_for` in `projecthub_slice1/apps/accounts/models.py`; `my_contact` in `projecthub_slice1/apps/accounts/views.py`; `projecthub_slice1/static/js/password-toggle.js`. Tests: `StudentIdFormatTests` and `PasswordToggleTests` in `apps/accounts/tests.py`, and `apps/accounts/tests_contact.py`.

## Purpose

A university does not hand out usernames, so people sign in with what they already have: their Baze email, or for students their full student ID. Contact details let students, alumni and staff reach each other for collaboration or information. A personal email matters most for alumni, because their Baze email may close after they graduate. Each person decides who may see each of their details.

## Files involved

Paths are relative to `projecthub_slice1/`.

| File | Role in the feature |
|---|---|
| `config/settings.py` | `STUDENT_ID_REGEX` and `STUDENT_ID_HELP`: the Baze format `BU/<year><batch A-C>/<department code>/<number>`, changeable in `.env` |
| `apps/accounts/forms.py` | `ProjectAuthenticationForm` finds the account by Baze email, then by student ID, then by plain username; `clean_student_number` upper-cases and checks the ID; `ContactDetailsForm` edits the personal email and phone and refuses a Baze address as the personal email |
| `apps/accounts/models.py` | `User.personal_email`, `User.phone` and their two visibility fields; `ContactVisibility` (only me, staff only, all signed-in Baze users); `phone_validator`; `User.contact_for(viewer)` decides what a viewer may see |
| `apps/accounts/migrations/0009_contact_details_on_user.py` | Moved the old student-only `contact_email` to `User.personal_email`, keeping each student's earlier consent |
| `apps/accounts/views.py`, `templates/accounts/contact.html` | The **My details** page (`/account/contact/`), linked from the menu for every signed-in person |
| `apps/accounts/templatetags/contact.py`, `templates/projects/project_detail.html` | `{% contact_for person as rows %}` shows the student's and the supervisor's shared details on a project page |
| `templates/portals/student_current.html` | Reminds a current student without a personal email to add one before graduating |
| `static/js/password-toggle.js`, `static/css/app.css` | The eye button on every password field |
| `apps/accounts/views.py` (`manage_staff_account`, `manage_student_account`), `templates/admin_tools.html`, `templates/accounts/student_manage.html` | The administrator corrects account details and resets passwords; students are found with the search under **Student accounts** |

## Flow

1. **Adding a student:** the coordinator (own department) or the administrator enters the student's details under **Add student** (`add_student_account`). The full ID, for example `bu/23b/it/7892`, is upper-cased to `BU/23B/IT/7892`, checked against `STUDENT_ID_REGEX`, and refused if another student has it. The account is active at once; the student signs in with a temporary password and chooses their own. Students cannot create accounts themselves (D-28).
2. **Signing in:** the sign-in box accepts the Baze email or the full student ID, in any case. The short number `7892` alone is refused, because another year or department can have the same number. A plain username still works underneath, for the demo accounts and the administrator created on the server.
3. **My details:** anyone signed in opens **My details**, sees their Baze email (fixed) and edits their personal email, phone number, and who can see each one.
4. **Showing details:** on a project page, `contact_for` returns only the details the viewer may see: everything to the owner, "staff only" details to supervisors, coordinators, HODs and administrators, "all signed-in Baze users" details to anyone signed in. Hidden details are never sent to the page.
5. **Passwords:** the eye button switches a password field between hidden and visible text, and the field goes back to hidden when the form is sent.
6. **Mistakes:** if someone entered wrong details or forgot their password, the administrator finds them in System administration and corrects the name, Baze email, student ID or programme, or resets the password. A corrected email moves the sign-in and sends a notice to the new address; every change is audited.

## Rules

- **The Baze email is the sign-in.** Its owner cannot change it on My details. An administrator can correct a staff member's Baze email, including their own, on that person's page in System administration; the sign-in moves to the new address and a notice is sent to it. Everything else on My details belongs to its owner.
- **Contact details are opt-in.** New details start as "Only me". Nothing is ever shown to people who are not signed in (D-09).
- **The full student ID, not the short number.** It is unique; the last digits alone are not.
- **One setting for the ID format.** If Baze's format differs, change `STUDENT_ID_REGEX` and `STUDENT_ID_HELP` in `.env` together.
- **The administrator fixes mistakes** (D-26), but never reactivates an unapproved registration, and never changes the programme of a student who already has a project.
- **Not verified:** the personal email and phone format are checked, but no confirmation code is sent (`docs/known_limits.md`).

## Self-test

1. A coordinator types `bu/23b/it/7892` when adding a student. What is stored, and why is it accepted?
2. Why can a student not sign in with just `7892`?
3. A student sets their phone to "Staff only". Who sees it on their project page?
4. Why does the system ask for a personal email when every student already has a Baze email?
5. Where would you change the student ID format if Baze's department codes can be five letters long?

<details>
<summary>Answers</summary>

1. `BU/23B/IT/7892`. `checked_student_id` upper-cases the input before checking it against `STUDENT_ID_REGEX`, so the case typed does not matter.
2. The number can repeat in another year or department, so it could match the wrong student. Only the full ID is unique.
3. The student themself, and supervisors, coordinators, HODs and administrators. Other students and alumni do not (`User.contact_for`).
4. The Baze email may close after graduation. A personal email keeps alumni reachable for collaboration and information.
5. `STUDENT_ID_REGEX` (and its message, `STUDENT_ID_HELP`) in `.env`; the default is in `config/settings.py`. For five letters, change `[A-Z]{2,4}` to `[A-Z]{2,5}`.

</details>
