# Registration status page

> **Applies only when self-registration is switched on** (`STUDENT_SELF_REGISTRATION=True` in `.env`). It is off by default: students are added by their coordinator or the administrator (D-28), so they never wait for approval.

After a student registers, they land on a page that shows whether their registration is **waiting for review**, **approved** or **not approved**, and it updates itself when the administrator decides. It is opened by a signed link, not by typing an email address, so it cannot be used to find out who has registered.

Code: `registration_status`, `registration_status_token` and `_registration_for_token` in `projecthub_slice1/apps/accounts/views.py`. Tests: `RegistrationStatusPageTests` in `projecthub_slice1/apps/accounts/tests.py`.

## Purpose

A new student account stays inactive until an administrator approves it. Without this page, the student only found out by trying to sign in now and then. The status page answers "where is my registration?" straight away. Together with the decision email and the "Account approved" alert waiting at first sign-in, the student is never left guessing.

## Files involved

| File | Role in the feature |
|---|---|
| `apps/accounts/views.py` | `register_student` redirects to the page after a successful sign-up; `registration_status_token` makes the signed link; `registration_status` shows the page or, with `?format=json`, the status for the poller; `_rejection_reason` finds the administrator's reason in the audit log |
| `apps/accounts/urls.py` | `register/status/<str:token>/`, named `registration_status` |
| `templates/registration/status.html` | One panel each for pending, approved and rejected; only the current one is visible |
| `static/js/poll.js` | The shared 30-second poller, also used by the live counters |
| `static/js/registration-status.js` | Shows the right panel when the poller reports a new status, and stops once it is decided |
| `templates/base.html` | Loads `poll.js`, then the page's own scripts through `{% block scripts %}` so the order is right |
| `config/settings.py` | `REGISTRATION_STATUS_MAX_AGE_DAYS` (default 30): how long a link keeps working |

## Flow

1. The student submits the sign-up form. `StudentRegistrationForm.save()` creates an inactive student with registration status **pending**.
2. `register_student` builds a token with `django.core.signing.dumps(student.pk, salt=...)` and redirects to `/register/status/<token>/`.
3. The page reads the token back with `signing.loads(..., max_age=30 days)`. A token that was changed, made for a different purpose (salt), belongs to a non-student, or is too old is refused: the page says the link is not valid, and the JSON answer is 404.
4. The page shows the panel for the current status. The poller waits 30 seconds, then asks `?format=json` every 30 seconds while the tab is visible; it pauses while the tab is hidden and catches up when it comes back.
5. The administrator approves or rejects in System administration. That saves the decision, writes the audit entry (with any reason), sends the email, and on approval creates the "Account approved" alert.
6. The next poll returns `approved` or `rejected` (with the reason). The script switches panels and stops polling, because nothing more will change.

## Rules

- **No account enumeration.** There is no page that takes an email or student ID and returns a status. Only the person who just registered receives the link, and the token cannot be forged without the server's `SECRET_KEY`.
- **The token holds only the account's id**, signed with a salt specific to this feature, so a token from another part of the site cannot be reused here.
- **Links expire** after `REGISTRATION_STATUS_MAX_AGE_DAYS`. Once expired, the student can still check by signing in: with the correct password, the login page says "still awaiting approval" or "was not approved".
- **Only the student's own status and first name are shown**: no other personal data. Responses carry `Cache-Control: no-store`.
- **Polling stops** on a decision, on 404 (invalid link) and while the tab is hidden, so an open tab costs at most one small request every 30 seconds.

## Self-test

1. Why is there no "check my status" form where a student types their email?
2. What would happen if someone changed one character of the token in the address bar?
3. A student opens their status link 45 days after registering. What do they see, and how can they still find out their status?
4. Which file contains the 30-second polling logic, and which other feature uses it?
5. The administrator rejects a registration with the reason "Wrong programme selected." Trace how that reason reaches the student's open status page.

<details>
<summary>Answers</summary>

1. Anyone could type any email and learn whether that person has registered, and whether they were approved or rejected (account enumeration). A signed link given only to the registrant avoids that.
2. `signing.loads` raises `BadSignature`, so the page shows "This status link is not valid" (404) and the JSON answer is 404, which also stops the poller.
3. The link is older than the 30-day maximum, so it is refused as not valid. They can sign in with their email and password: the login page tells a pending or rejected account its status, but only when the password is correct.
4. `static/js/poll.js` (`ProjectHubPoll`). The live counters (`static/js/live-counters.js`: the Alerts badge and the admin and coordinator portal counters) use it too.
5. `review_student_registration` saves the rejection and writes an audit event with `details={"reason": ...}`. On the next poll, `registration_status` sees status `rejected`, `_rejection_reason` reads the latest rejection event for that account, and the JSON includes the reason. `registration-status.js` shows the "Not approved" panel, fills in the reason, and stops polling.

</details>
