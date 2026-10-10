# Automation: `run_automation`

```
python manage.py run_automation                        # run the checks once, then exit
python manage.py run_automation --loop                 # keep running, one run every 60 seconds
python manage.py run_automation --loop --interval 300  # one run every 5 minutes
```

> **Nothing happens on its own.** The web server never runs these checks. Reminders are created only while **either** a scheduler (Windows Task Scheduler or cron) starts `run_automation` on a timetable, **or** a `run_automation --loop` process is kept running. If neither is running, no alerts are sent, however long a registration waits or a project stalls.

Code: `projecthub_slice1/apps/supervision/automation.py` (the checks), `apps/supervision/management/commands/run_automation.py` (the command), `notify()` in `apps/supervision/services.py`, model `Notification` (`apps/supervision/models/notification.py`, migration `supervision/0007_notification`). Tests: `RunAutomationTests` in `apps/supervision/tests.py`.

## What one run does

| Check | Flags | Notifies | Link in the alert |
|---|---|---|---|
| `at_risk_project` | Active projects whose [health score](health-score.md) is in the At risk band (above 60) | The project's supervisor and every active coordinator in its department | Project workflow |
| `pending_registration` | Real (non-demo) student registrations still pending more than 48 hours after sign-up | Every active admin | Admin tools |
| `unacknowledged_notice` | Notices that require acknowledgement, posted more than 48 hours ago | Each approved, not-graduated student in the notice's audience who has not acknowledged it | Notices page |

The audience follows the same rules as the notices page: a project notice reaches that project's student, a department notice reaches the department's students, and a notice with no department reaches everyone.

Alerts appear on the **Alerts** page (`/supervision/alerts/`), with an unread count next to "Alerts" in the menu. They are called Alerts in the interface because the student menu already uses "Notifications" for supervisor notices.

The hour limits are settings: `AUTOMATION_PENDING_REGISTRATION_HOURS = 48`, `AUTOMATION_NOTICE_ACK_HOURS = 48`, `NOTIFICATION_DEDUP_HOURS = 24`.

## Why running it twice is safe (idempotency)

Every alert goes through `notify(recipient, kind, obj, ...)`. Before creating a row, it checks for a notification with the **same recipient, kind and object** (model label + primary key) created in the **last 24 hours**. If there is one, it creates nothing and returns `None`. So:

- running the command again a minute later creates nothing new (tested: `test_second_run_creates_nothing_new`);
- a problem that is still there the next day produces one reminder a day, not one a minute;
- a different person, kind or object is a separate alert.

The check and the insert happen in one transaction, with the recipient's user row locked. Two runs that overlap (for example, a scheduled run and a forgotten `--loop` window) therefore cannot both create the same alert.

## The run summary

Each run logs one line to standard output, with a timestamp:

```
2026-10-08 09:00:00,123 INFO run_automation: 6 new notifications | at_risk_project: 1 flagged, 2 new, 0 already sent | pending_registration: 1 flagged, 1 new, 0 already sent | unacknowledged_notice: 2 flagged, 3 new, 0 already sent
```

- *flagged* is the number of records found.
- *new* is the number of notifications created.
- *already sent* is the number skipped by the 24-hour rule.

With `--loop`, a run that fails is logged with its traceback and the loop carries on. Ctrl+C stops it. To keep the log, redirect the output to a file, as in the examples below. Log files are not committed: keep them outside the repository, or in a `logs/` folder you add to `.gitignore`.

## Scheduling on Windows: Task Scheduler

Run it every 15 minutes, using the project's virtual environment.

1. Create `run_automation.cmd` next to `manage.py`. In both steps below, replace `<path-to-repo>` with the folder you cloned the repository into (for example `C:\Dev\baze-projecthub`):
   ```bat
   @echo off
   cd /d <path-to-repo>\projecthub_slice1
   .venv\Scripts\python.exe manage.py run_automation >> "%USERPROFILE%\projecthub-automation.log" 2>&1
   ```
2. Register the task (one line, in a Command Prompt):
   ```bat
   schtasks /Create /TN "ProjectHub automation" /TR "<path-to-repo>\projecthub_slice1\run_automation.cmd" /SC MINUTE /MO 15 /F
   ```
   Or in the Task Scheduler window: *Create Basic Task* → trigger *Daily*, then in the task's properties set *Repeat task every 15 minutes for 1 day*. The action is *Start a program* with the `.cmd` file.
3. Check it: `schtasks /Run /TN "ProjectHub automation"`, then look at the end of `%USERPROFILE%\projecthub-automation.log`.

By default the task runs only while you are logged in. To run it when signed out, choose *Run whether user is logged on or not* in its properties.

## Scheduling on Linux or macOS: cron

`crontab -e`, then add (adjust the paths):

```cron
*/15 * * * * cd /srv/projecthub/projecthub_slice1 && .venv/bin/python manage.py run_automation >> /var/log/projecthub/automation.log 2>&1
```

Cron gives the command a minimal environment. The database settings must therefore come from the project's `.env` file (as they do now), not from variables set in your shell.

## Or: keep a `--loop` process running

```
python manage.py run_automation --loop --interval 300
```

This suits a demo or a single server. The process must stay open: closing the terminal, logging out or restarting the machine stops the reminders. For a server, run it under a service manager (systemd, NSSM on Windows) so it restarts automatically. Use **either** the loop **or** a scheduler, not both. Running both is harmless, because of the 24-hour rule, but pointless.

## Limits

- Reminders are in-app only: no email or SMS.
- At-risk alerts inherit the health score's limits: hand-picked heuristic weights, and milestones that today can only be added in Django admin.
- A reminder repeats daily for as long as the condition holds. Reading an alert does not stop the next day's reminder; fixing the cause does (acknowledging the notice, reviewing the registration, or bringing the project back under the at-risk band).
