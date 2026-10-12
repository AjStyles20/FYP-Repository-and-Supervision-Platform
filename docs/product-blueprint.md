# Baze Project Hub — Product Blueprint

**Status:** Working product design for the real application
**Scope:** Pilot in the author's faculty and department; data model and navigation support Baze University-wide expansion.

**Implemented slices:** Authenticated Current/Past repository and protected document downloads; department-scoped supervisor allocation with recorded reassignment history; individual staff assignment authority and personal supervision history.

## Product purpose

Baze Project Hub gives students and academic staff one place to discover final-year work, reduce accidental topic duplication, manage supervision and approvals, and preserve completed projects and their documented research gaps.

The system is not a public internet repository. Project discovery is available to authenticated Baze Project Hub users. The application must not imply that an email address is verified by checking its domain alone; account registration is reviewed by an administrator.

## Product principles

1. **Discoverability with privacy:** project topics and approved project summaries can be found across Baze by signed-in users. Student IDs remain staff-only. Contact details (personal email, phone) are opt-in per detail: each person chooses who sees each one (D-21).
2. **One academic hierarchy:** Faculty → Department → Programme → Qualification/award (for example BSc, BA, MSc or MA) → Project.
3. **Pilot narrowly, expand by configuration:** launch with the author's faculty and department; add other faculties, departments, programmes and awards as academic data, not new application branches.
4. **Keep evidence scoped:** project metadata can be discoverable across Baze, but individual meeting discussions and corrective-action notes are shared only with the student, assigned supervisor and authorized academic staff.
5. **Use explicit decisions for consequential actions:** role-checked approvals, defence outcomes, completion and HOD archive sign-off are recorded with an actor, time and history.
6. **Do not claim external verification:** graduation status is recorded only after an authorized person confirms it; there is no assumed connection to Baze's student-record system.
7. **Build an accessible, light interface:** responsive server-rendered pages, clear hierarchy, readable tables/cards, and minimal client-side JavaScript.

## Navigation and main areas

### Public entry (unauthenticated)

- **Sign in:** Baze email, or a student's full student ID (like `BU/23B/IT/7892`).
- **Create student account:** choose current final-year student or past final-year student; provide Baze email, student ID, programme/award and password. Registration remains pending until admin review.
- Staff and administrator accounts are created or provisioned by an administrator, never selected through public registration.

### Authenticated application

1. **Home / Dashboard**
   - Student: own project, current stage, next action, supervisor, upcoming meetings and notices.
   - Supervisor: supervisee counts, pending proposals, upcoming meetings and recent project activity.
   - Coordinator: department assignment and approval queues, supervisor capacity summaries.
   - HOD: department project completion and sign-off queue.
   - Admin: account approvals and academic-structure administration.
2. **Repository**
   - Two primary views: **Past students** and **Current students**.
   - Search by project title/topic, student name and supervisor; student ID search is staff-only.
   - Cascading filters: faculty → department → programme/award → year.
   - A supervisor search result can open that supervisor's current and past project list.
3. **Project details**
   - Shared project information according to its visibility and publication state.
   - Past project details include its summary, dates, academic unit, student name, recorded completion/graduation year when verified, final and previous supervisors, documented gap and approved downloadable files.
   - Current project details show only approved public-facing fields; private supervision notes are never rendered here.
4. **My Project**
   - Student's proposal, assigned supervisor, timeline, approvals, stage history, meeting count and permitted meeting records.
   - Student submits work and may confirm or dispute a meeting record; edits to records are versioned.
5. **Supervisor Workspace**
   - Current supervisees and history of past supervisees/projects. The current page shows only work assigned to that staff member, not the department's complete project list.
   - Project stage, approved/defended counters, pending actions, attendance counts and meeting summaries.
   - Supervisor can record meeting details, publish notices/resources, and schedule meetings.
   - Meeting discussions/corrections remain visible only to the student and authorized staff.
6. **Coordinator Workspace**
   - Assign/reassign students and supervisors within the department; keep assignment history. Assignment authority is granted independently of job title, so a supervisor, coordinator or HOD may be delegated this responsibility. The initial project-assignment workspace is implemented; student proposal intake and further workflow actions remain future slices.
   - Supervisor workload and counters (current, approved, defended).
   - Digital approval-form queue and approval/defence recording.
7. **HOD Workspace**
   - Completion review and final sign-off.
   - Archive is performed by the HOD only after project requirements are confirmed and the required gap and documents are recorded.
8. **Project Guide**
   - Plain-language stages from idea to archive, department process information and downloadable official PDFs.
9. **Admin**
   - Review student registrations; manage staff accounts and the faculty/department/programme/award tree; configure policy and import approved data.

## Repository visibility and record lifecycle

The repository's current/past sections are derived views of project and student lifecycle state, not separate duplicate project records.

- **Current:** projects that have not passed authorized completion and HOD archive.
- **Past:** completed projects archived by the HOD, with approved metadata and files.
- A project is not archived merely because a defence was recorded. The HOD records the required sign-off after confirming the department's completion conditions.
- When the HOD records FYP completion and sign-off, the project is automatically moved from Current to Past.
- Project completion and student graduation are separate facts. The HOD verifies graduation separately; graduation year must not be inferred from project completion or generated automatically without that confirmation.
- A project can be listed as past work while the student's university graduation status remains unverified; the record must label these states accurately.

## Supervisor history and meeting privacy

- Supervisor profile/history is searchable by signed-in Baze users and lists the supervisor's project records subject to project visibility.
- Published supervisor counters may show aggregate counts (current, approved, defended, archived). They must not expose confidential notes.
- A meeting record contains the scheduled time/venue, attendance, discussion, corrections/actions and project progress.
- The student, assigned supervisor and authorized coordinator/HOD can access the record; both parties can see attendance counts. All changes preserve prior versions.
- Notices and resource shares are visible to their intended supervisees; acknowledgement time is recorded where required.

## Visual direction

- Use a clean academic workspace rather than a bare Django form page: a persistent header, role-aware left navigation on desktop, clear page titles and breadcrumbs, compact dashboard cards, readable project cards, a filter/search toolbar, and a responsive table/card toggle for project lists.
- Use a restrained deep-navy and teal palette until the official Baze brand palette is confirmed. Keep high-contrast text, visible status labels with text (not color alone), consistent form help/error messages, and clear primary actions.
- Prioritize phone layouts for search, project summaries, meeting schedules and notices. Large coordinator/HOD queues may use horizontally scrollable tables with a usable stacked mobile presentation.
- Keep forms progressive: request only necessary account fields at registration; group approval, meeting and archive forms into clearly labeled sections.

### Repository page sketch

```text
Project Repository                               [Profile]
Find work before choosing a topic
[Search title, student, supervisor...] [Faculty v] [Department v] [Programme v] [Year v]
[Current students] [Past students]

Project card/list row:
  Project title                         [In progress / Archived]
  Student · Programme · Department
  Supervisor · Year                     [View project]
  Short abstract and selected tags
```

On Past students, the detail page adds the documented gap, final/previous supervisor, completion and verified graduation details, the contact details the student chose to share, and files the department has approved for Baze-wide access. On Current students, show only the project description, stage and supervisor details approved for repository discovery.

### Role workspace sketch

Each role lands on a focused work queue, not the same generic dashboard: students see their next project action; supervisors see advisees and meeting/notice tasks; coordinators see assignments and approval forms; HODs see completion sign-offs; admins see pending account reviews and academic data tools.

## Delivery sequence

### Foundation already implemented

- Django accounts, academic hierarchy, role checks, login, student registration review and initial project data models.

### First product slice: repository

- Searchable Current/Past views with faculty/department/programme/year filters.
- Project detail pages with correct role-aware field visibility.
- Staff-only student ID search; contact details shown only as their owner chose.
- Project document metadata and permission-checked downloads with per-file Baze-user/staff visibility.
- Pilot academic data only for the author's faculty/department; structure stays reusable.

Current implementation status: the authenticated repository, search/filter views, project detail pages, download controls, demo repository data, and role-aware ID/contact visibility are implemented. Uploaded files are administered through Django Admin and downloads pass through the authenticated application route; do not expose the media directory as public static files. Public-facing document upload, coordinator/supervisor assignment history entry, and HOD archive actions are separate workflow slices.

### Next slice: student/supervisor workspaces

- Student proposal and lifecycle page.
- Supervisor student list, meeting records, attendance counts, notices and resources.
- Meeting visibility restrictions, confirmation/dispute, and version history.

### Next slice: coordinator/HOD workflow

- Assignments with history and capacity counters.
- Digital approval form and department-specific policy configuration.
- Approval, submission, defence, completion, and HOD-only archive transitions.
- Archived record publication in Past students.

### Later operational capabilities

- Official guide PDFs, richer audit tools, CSV import/export and department-by-department onboarding.
- Similar-topic recommendations and other AI assistance only after core search and workflow are reliable and the labelled evaluation data can be created ethically.

## Decisions to confirm with the department

- Exact data fields and evidence required on the approval form.
- The department's approval and defence chain, correction loop and definition of completion.
- Which past-project documents may be shared with all authenticated users and which require staff-only or owner-only access.
- Whether student name publication and contact opt-in wording meet Baze policy and Nigeria Data Protection Act requirements.
- How an administrator is authorized to confirm a graduation year where there is no student-record-system integration.
