# Live counters: `/api/summary/`

Every signed-in page refreshes the Alerts count in the menu every 30 seconds without reloading. The admin and coordinator portals also refresh their four counters.

Code: `api_summary`, `admin_counts` and `department_counts` in `projecthub_slice1/apps/accounts/views.py`; the poller is `projecthub_slice1/static/js/live-counters.js`. Tests: `SummaryApiTests` in `projecthub_slice1/apps/accounts/tests.py`.

## Request

```
GET /api/summary/
```

It is signed in with the normal session cookie; there is no token. Only `GET` is accepted (`POST` and other methods get 405). Every response carries `Cache-Control: no-store`.

## Responses

| Status | When | Body |
|---|---|---|
| 200 | Signed in as an **admin** or a **coordinator** | `role`, `counters`, `unread_notifications`, `generated_at` |
| 200 | Signed in with **any other role** (student, supervisor, Head of Department) | `role`, `unread_notifications`, `generated_at`; no `counters` |
| 401 | Not signed in | `{"detail": "Sign in required."}` |
| 405 | Any method other than GET | empty |

The 401 is JSON on purpose, not a redirect to the login page, so the script can tell "signed out" apart from an error and stop. No signed-in role is refused. Each role sees only numbers it is allowed to see: its own unread count, plus portal counters for the two roles that have them.

### 200 for an admin

```json
{
  "role": "admin",
  "counters": {
    "pending_count": 1,
    "student_count": 42,
    "staff_count": 9,
    "programme_count": 3
  },
  "unread_notifications": 2,
  "generated_at": "2026-10-08T10:15:30.123456+00:00"
}
```

**Demo rows follow the viewer** (`for_viewer` in `apps/accounts/views.py`): a demo account (`is_demo`) counts demo **and** real rows, so `demo.admin` and `demo.coordinator` see the demo story; a real account counts real rows only, so sample data never inflates real numbers. The lists beside the counters (registrations on the admin portal and Admin tools, the coordinator and Head of Department portal lists) use the same rule, so a number and its list agree.

| Key | Meaning | Real viewer counts | Demo viewer counts |
|---|---|---|---|
| `pending_count` | Student registrations waiting for review | Real rows | Demo and real rows |
| `student_count` | Active student accounts | Real rows | Demo and real rows |
| `staff_count` | Active supervisor, coordinator and Head of Department accounts | Real rows | Demo and real rows |
| `programme_count` | Programmes | Real rows | Demo and real rows |

### 200 for a coordinator (their whole faculty, D-29)

```json
{
  "role": "coordinator",
  "counters": {
    "active_count": 8,
    "unassigned_count": 1,
    "approval_count": 1,
    "defence_count": 1
  },
  "unread_notifications": 0,
  "generated_at": "2026-10-08T10:15:30.123456+00:00"
}
```

| Key | Meaning |
|---|---|
| `active_count` | Projects in any department of the coordinator's faculty that are not archived (demo projects only for a demo viewer, as above) |
| `unassigned_count` | Of those, projects with no supervisor |
| `approval_count` | Projects at "Supervisor accepted", whose signed form the coordinator must log |
| `defence_count` | Projects at "Submitted for examination", whose defence outcome must be recorded |

### 200 for every other role (student, supervisor, Head of Department)

```json
{
  "role": "supervisor",
  "unread_notifications": 1,
  "generated_at": "2026-10-08T10:15:30.123456+00:00"
}
```

There is no `counters` key at all: these roles have no portal counters to refresh.

### Fields

- `role`: the caller's own role.
- `counters` (admins and coordinators only): integers only. The keys are exactly the context names the portal templates use, and the page marks each number with `data-counter="<key>"`. That is how the script finds what to update. The numbers come from the same functions the portal page uses, so the page and the API cannot disagree (tested: `test_counters_match_the_portal_page`).
- `unread_notifications`: the caller's own unread Alerts (see [automation](automation.md)). Never anyone else's.
- `generated_at`: server time in ISO 8601 (UTC).

**No personal data:** the body never contains names, usernames, emails, student numbers or alert titles. Only counts and the caller's own role are included (tested: `test_response_contains_numbers_only_and_no_personal_data`, `test_other_roles_get_only_their_own_unread_count`).

## The poller (`static/js/live-counters.js`)

`base.html` loads it for every signed-in user. It:

1. waits 30 seconds after the page loads, since the page already has fresh numbers;
2. fetches `/api/summary/`, writes each counter (if any) into its `[data-counter]` element, and writes the unread count into the Alerts badge. The badge is hidden at 0, and the link's `aria-label` is updated for screen readers;
3. schedules the next request 30 seconds later;
4. **stops while the tab is hidden** (`visibilitychange`): no requests are made until the tab is visible again, and then one request is sent straight away;
5. stops for good on 401 or 403. On a network or server error it keeps the old numbers and tries again at the next tick.

This was checked in a real browser (headless Chromium) against the demo server:
- an alert created on the server appeared in the badge at the first 30-second poll, without a reload;
- no requests were sent during 35 seconds with the tab hidden;
- one request was sent as soon as the tab became visible again.

## Not covered

- It is polling, not push. A change can take up to 30 seconds to appear.
- Every open signed-in tab makes one small request every 30 seconds while visible. That is fine at department scale; a large deployment would want a longer interval or server push.
