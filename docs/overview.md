# Baze Project Hub

**Working title:** Design and Implementation of a Final-Year Project Repository and Supervision Management Platform for Baze University
**Status (2026-10-05):** The Django application is under active implementation. Supervisor has given a verbal go-ahead; the project approval form is **not yet signed**. Title not final.
**Author:** Aj (Computer Science, Baze University, Abuja)

---

## 1. What this is

A web application that does two connected jobs for final-year projects (FYPs):

1. **Repository.** Past and current projects are searchable, so students can see what has been done and avoid repeating or copying topics. Past projects keep their documented gap, final supervisor, earlier supervisor and downloadable files.
2. **Supervision management.** Supervisor assignment, configurable approval, meetings, notices, availability, and a trustworthy record of what happened and when.

It begins with the author's own faculty and department. The data model includes Faculty, Department and Programme so the same system extends to other faculties later.

## 2. Planning files in this folder

The full list of docs, including the code map, explainers, diagrams and reviews, is in [`README.md`](README.md).

| File | Read it for |
|---|---|
| `overview.md` | This overview, setup and rules |
| `implementation_plan.md` | Architecture, workflows, security, stages, testing, risks |
| `task.md` | The working checklist, phase by phase |
| `walkthrough.md` | Current account flow and project workflow implementation status |
| `requirements.md` | Numbered requirements, with where each one came from |
| `decisions.md` | Decisions made, proposals, and open questions for the supervisor |
| `product-blueprint.md` | Product navigation, privacy boundaries, lifecycle and staged delivery |
| `database_schema.sql` | MySQL reference design (ER diagram source) |

Read order for a new developer or AI agent: `overview.md` → `product-blueprint.md` → `requirements.md` → `decisions.md` → `implementation_plan.md` → `database_schema.sql` → `task.md`.

## 3. Fixed constraints (do not change without asking the author)

- **Language/stack:** Python and HTML, built as a **web app**. **MySQL** database, designed in **MySQL Workbench** (reported as an HOD requirement; confirm).
- **No novelty requirement** from the school. A contribution still has to be explained at the defence.
- **No imported student roster or project records.** The school will not release student data to other students. Students submit their own account details; an administrator reviews student IDs before activating accounts. Development fixtures are synthetic, and old students' FYPs are not collected.
- **Only the HOD signs off and archives** a project into the past-projects repository.
- **Approval varies by supervisor.** There is no single fixed rule.

## 4. Proposed stack (confirm in `decisions.md`)

- **Django 5.2 (Python 3.14)** monolith, server-rendered HTML templates, plain CSS, a little JavaScript (HTMX optional)
- **MySQL 8** (InnoDB, `utf8mb4`) with the `mysqlclient` driver
- Uploaded files stored on disk (not in the database), served only through permission-checked views
- Optional later: scikit-learn / sentence-transformers for the topic-similarity module

### Proposed repository layout

```text
projecthub/
  manage.py
  config/                 # settings, urls
  apps/
    accounts/             # users, roles, login
    academics/            # faculty, department, programme
    projects/             # projects, status history, approvals, documents, repository search
    supervision/          # assignments, policies, meetings, records, availability, notices
    audit/                # append-only audit log
  templates/              # HTML templates
  static/                 # css, js
  media/                  # uploaded files (never committed)
  docs/                   # this folder
```

## 5. Local setup (outline)

1. Install Python 3.14, MySQL Server 8.4 and MySQL Workbench.
2. Create a virtual environment and install Django and `mysqlclient`.
3. In MySQL: create the database `baze_projecthub` (utf8mb4) and an application user with only the privileges it needs (see the end of `database_schema.sql`).
4. Put database credentials in environment variables, **never in source control**.
5. Run migrations, then the demo-seed command (see `task.md`, Phase C).
6. Use Workbench's reverse-engineer feature on the finished database to produce the ER diagram for the report.

> **One source of truth:** write Django models and migrations. Do not also edit tables in Workbench, or the two will drift. `database_schema.sql` is a design reference.

## 6. Golden rules for anyone writing code here

1. **Enforce permissions on the server**, never only by hiding buttons.
2. **History is never overwritten.** Supervisor changes, status changes and record edits add rows.
3. **Audit log is append-only.** The application account must not be able to update or delete it.
4. **Mark demo rows `is_demo = 1`** so they can be removed in one step.
5. **Student IDs** are visible to staff only. Contact details (personal email, phone) are each person's own, and each is shown only to the audience its owner chose: only me (the default), staff only, or all signed-in Baze users.
6. **No secrets in the repository.** Passwords hashed with Django's default hasher. CSRF protection on all forms.
7. **Keep scope tight.** This is not an ERP, an LMS or a timetable system.

## 7. Glossary

- **FYP** final-year project (undergraduate), including master's projects when added
- **Supervisor** the lecturer supervising a student's project
- **Coordinator** the lecturer who assigns students to supervisors and records approvals and defence outcomes
- **HOD** head of department; final sign-off and archive
- **Gap** what a finished project did not cover, recorded for later students to continue
- **Project status vs student status:** completing a project does not mean graduating. They are separate fields.
