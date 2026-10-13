# Docs

All project documentation lives in this folder. Code paths mentioned inside these files are relative to `projecthub_slice1/` unless a file says otherwise.

New here? Read [`overview.md`](overview.md) first, then [`code_map.md`](code_map.md).

## Start here

| File | Read it for |
|---|---|
| [`overview.md`](overview.md) | What the system is, fixed constraints, golden rules, glossary |
| [`code_map.md`](code_map.md) | "To change X, open file Y, look for Z" (checked by `apps/accounts/tests_docs.py`) |
| [`walkthrough.md`](walkthrough.md) | Current account flow and project workflow, as implemented |
| [`known_limits.md`](known_limits.md) | What the system does not do yet, stated plainly |
| [`feature-comparison.md`](feature-comparison.md) | The features an FYP management system is expected to have, and which are built here |

## Planning and decisions

| File | Read it for |
|---|---|
| [`product-blueprint.md`](product-blueprint.md) | Navigation, privacy boundaries, lifecycle and staged delivery |
| [`requirements.md`](requirements.md) | Numbered requirements and where each came from |
| [`decisions.md`](decisions.md) | Decisions made, proposals, and open questions for the supervisor |
| [`implementation_plan.md`](implementation_plan.md) | Architecture, workflows, security, stages, testing, risks |
| [`task.md`](task.md) | The working checklist, phase by phase |
| [`database_schema.sql`](database_schema.sql) | Early MySQL reference design. Django models are the source of truth |

## How features work

| File | Feature |
|---|---|
| [`explain/registration-status.md`](explain/registration-status.md) | Registration status page behind a signed link |
| [`explain/live-counters.md`](explain/live-counters.md) | `/api/summary/` and the 30-second live counters |
| [`explain/automation.md`](explain/automation.md) | The `run_automation` command and scheduling it |
| [`explain/health-score.md`](explain/health-score.md) | Project health score |
| [`explain/similarity.md`](explain/similarity.md) | Similar-topic checker |
| [`explain/admin-integrity.md`](explain/admin-integrity.md) | Why the Django admin cannot bypass the workflow, and the admin hub |
| [`explain/accounts-and-contact.md`](explain/accounts-and-contact.md) | Student ID format, signing in, My details (contact visibility) and the password eye button |

## Diagrams and screenshots

| File | Contents |
|---|---|
| [`diagrams/README.md`](diagrams/README.md) | Mermaid sources (ER, project states, HOD sign-off, architecture, use cases) and how each was checked |
| [`screenshots/`](screenshots/) | Admin portal, project guide, repository and workflow pages at 1280 px and 360 px (current look, 2026-10-13) |

## Demo, defence and reviews

| File | Read it for |
|---|---|
| [`demo_script.md`](demo_script.md) | A 7-minute demo, one role per step |
| [`sample_import.csv`](sample_import.csv) | Demo-only CSV for **Import past projects**; imports after `seed_demo` |
| [`defence/defence-qa.md`](defence/defence-qa.md) | Likely defence questions with short answers |
| [`review/01-inventory-and-workflows.md`](review/01-inventory-and-workflows.md) | Code review: inventory, history, workflows, permissions, data model |
| [`review/02-admin-and-ui-questions.md`](review/02-admin-and-ui-questions.md) | Code review: admin portal and UI questions |
