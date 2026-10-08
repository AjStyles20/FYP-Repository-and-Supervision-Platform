# Live counters: `/api/summary/`

The admin and coordinator portals refresh their four counters, and the Alerts count in the menu, every 30 seconds without reloading the page.

Code: `api_summary`, `admin_counts` and `department_counts` in `projecthub_slice1/apps/accounts/views.py`; the poller is `projecthub_slice1/static/js/live-counters.js`. Tests: `SummaryApiTests` in `projecthub_slice1/apps/accounts/tests.py`.

## Request

```
GET /api/summary/
```

It is signed in with the normal session cookie; there is no token. Only `GET` is accepted (`POST` and other methods get 405). Every response carries `Cache-Control: no-store`.

## Responses

| Status | When | Body |
|---|---|---|
| 200 | Signed in as an **admin** or a **coordinator** | See below |
| 401 | Not signed in | `{"detail": "Sign in required."}` |
| 403 | Signed in as a student, supervisor or HOD | `{"detail": "Your role has no live counters."}` |
| 405 | Any method other than GET | empty |

The 401 is JSON on purpose, not a redirect to the login page, so the script can tell "signed out" apart from an error and stop.

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

| Key | Meaning |
|---|---|
| `pending_count` | Real (non-demo) student registrations waiting for review |
| `student_count` | Active, non-demo student accounts |
| `staff_count` | Active, non-demo supervisor, coordinator and HOD accounts |
| `programme_count` | All programmes, demo ones included |

### 200 for a coordinator (their own department only)

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
| `active_count` | Projects in the department that are not archived |
| `unassigned_count` | Of those, projects with no supervisor |
| `approval_count` | Projects at "Supervisor accepted", whose signed form the coordinator must log |
| `defence_count` | Projects at "Submitted for examination", whose defence outcome must be recorded |

### Fields common to both

- `role`: `"admin"` or `"coordinator"`.
- `counters`: integers only. The keys are exactly the context names the portal templates use, and the page marks each number with `data-counter="<key>"`. That is how the script finds what to update. The numbers come from the same functions the portal page uses, so the page and the API cannot disagree (tested: `test_counters_match_the_portal_page`).
- `unread_notifications`: the signed-in user's unread Alerts (see [automation](automation.md)).
- `generated_at`: server time in ISO 8601 (UTC).

**No personal data:** the body never contains names, usernames, emails or student numbers. Only the counts and the caller's own role are included (tested: `test_response_contains_numbers_only_and_no_personal_data`).

## The poller (`static/js/live-counters.js`)

`base.html` loads it only for admin and coordinator accounts. It:

1. waits 30 seconds after the page loads, since the page already has fresh numbers;
2. fetches `/api/summary/` and writes each counter into its `[data-counter]` element, and the unread count into the Alerts badge. The badge is hidden at 0, and the link's `aria-label` is updated for screen readers;
3. schedules the next request 30 seconds later;
4. **stops while the tab is hidden** (`visibilitychange`): no requests are made until the tab is visible again, and then one request is sent straight away;
5. stops for good on 401 or 403. On a network or server error it keeps the old numbers and tries again at the next tick.

This was checked in a real browser (headless Chromium) against the demo server:
- an alert created on the server appeared in the badge at the first 30-second poll, without a reload;
- no requests were sent during 35 seconds with the tab hidden;
- one request was sent as soon as the tab became visible again.

## Not covered

- Students, supervisors and HODs get 403, so their Alerts count refreshes only when a page loads. Extending the endpoint to them would mean returning just `unread_notifications` for those roles.
- It is polling, not push. A change can take up to 30 seconds to appear.
