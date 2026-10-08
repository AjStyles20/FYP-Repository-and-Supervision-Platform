# Project health score

A number from 0 to 100 that says how much an active project looks at risk, with the reasons behind it. It is shown only to supervisors and coordinators, to help them decide where to look first.

> **The weights, limits, bands and expected stage times are heuristics chosen by hand. They have not been validated against real project outcomes.** A high score is a prompt to check on a student, not evidence that anything is wrong. Validating the weights would need historical projects with known outcomes (for example, late submission or a failed defence) and a comparison of scores against them. That has not been done.

Code: `projecthub_slice1/apps/projects/services/health.py` (`health_score(project, now=None)`). Tests: `ProjectHealthScoreTests` in `projecthub_slice1/apps/projects/tests.py`. Settings: `HEALTH_*` in `projecthub_slice1/config/settings.py`.

## The formula

```
risk = 0.4 * min(days_since_last_meeting / 14, 1)
     + 0.3 * min(overdue_milestones / 3, 1)
     + 0.3 * min(days_since_stage_change / expected_days_for_stage, 1)

score = round(100 * risk)          # 0 = no warning signs, 100 = every term at its cap
```

Each term is capped at 1, so no single problem can contribute more than its weight: meetings at most 40 points, milestones 30, stage time 30.

| Term | What is counted | Source |
|---|---|---|
| Days since last meeting | Days since the most recent meeting with status **Held** whose time has passed. Scheduled, cancelled and missed meetings do not count. With no held meeting yet, days since the current supervisor was assigned; with no supervisor, days since the project was created. | `SupervisionMeeting.status`, `.scheduled_for`; `ProjectSupervisorAssignment.assigned_at`; `Project.created_at` |
| Overdue milestones | Milestones that are not done and whose due date is before today. Undated milestones never count. | `ProjectMilestone.due_date`, `.done` |
| Days since stage change | Days since the latest status event, divided by the expected days for the current stage. | `ProjectStatusEvent.created_at`; `HEALTH_EXPECTED_DAYS` |

**Expected days per stage** (`HEALTH_EXPECTED_DAYS`): Topic proposed 14, Supervisor accepted 14, Approved by the department 7, In progress 90, Submitted for examination 30, Defended 21. Completed or archived projects get no score.

## Bands

| Score | Band |
|---|---|
| below 30 | On track |
| 30 to 60 | Watch |
| above 60 | At risk |

`HEALTH_BANDS = {"watch": 30, "at_risk": 60}`. A score of exactly 30 or 60 is Watch.

## Reasons

Every score comes with one line per term showing the input, the limit and the points it added, for example:

- `No held meeting yet; supervisor assigned 20 days ago (limit 14 days): +40`
- `No milestones set: +0`
- `20 days at In progress (expected 90 days): +7`

That example totals 47, which is Watch. The points on each line are rounded separately, so they can differ from the total by 1.

## Worked example

A project In progress has its last held meeting 7 days ago, 1 overdue milestone, and has been at In progress for 45 days.

```
meeting    = 0.4 * min(7/14, 1)  = 0.4 * 0.5   = 0.20
milestones = 0.3 * min(1/3, 1)   = 0.3 * 0.333 = 0.10
stage      = 0.3 * min(45/90, 1) = 0.3 * 0.5   = 0.15
risk = 0.45  ->  score 45  ->  Watch
```

## Who sees it

| Viewer | Where |
|---|---|
| The project's supervisor | Workflow page, and each student on "Supervised students" |
| A coordinator in the project's department | Workflow page, and "Projects by health score" on the coordinator portal (top 8, highest first) |
| HOD, student, admin | Not shown |

A HOD or coordinator who is the assigned supervisor of a project sees its score as that project's supervisor.

## Known limits

- **Milestones can only be added in Django admin** today, and `seed_demo` creates none. Until a milestone page exists, that term is 0 for almost every project.
- **Stage time uses the moment the change was recorded**, not the date typed on the form. `seed_demo` records every change at seed time, so a freshly seeded demo shows nearly every project as On track.
- **A quiet period is not always a problem.** Exam weeks and holidays raise the meeting term for everyone at once.
- The score reads the database but never writes. A list page prefetches the four related tables, so the number of queries stays the same however many projects are listed.
