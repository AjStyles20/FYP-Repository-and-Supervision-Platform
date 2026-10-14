# Demo script: 7 minutes, one role per step

This walkthrough follows one department through a term. Each step is one role, about one minute. Every click below was checked against the seeded data with a scripted run of the same web addresses; all 42 checks passed.

All demo accounts use the password **`ChangeMe123!`** and log in with their **Baze email** (D-41): drop `demo.` and add `@bazeuniversity.edu.ng`. So `demo.adaeze` logs in as `adaeze@bazeuniversity.edu.ng`, and `demo.se.coordinator` as `se.coordinator@bazeuniversity.edu.ng`. The steps below name accounts by their short `demo.` name.

---

## Before the panel arrives (not part of the 7 minutes)

From `projecthub_slice1/`, in PowerShell:

```powershell
.\.venv\Scripts\python.exe manage.py purge_demo          # start from a clean story
.\.venv\Scripts\python.exe manage.py seed_demo           # about 10 seconds
.\.venv\Scripts\python.exe manage.py createsuperuser     # username: panel.admin, email: panel.admin@bazeuniversity.edu.ng (it logs in with that email, see step 7)
.\.venv\Scripts\python.exe manage.py runserver
```

1. Nothing to prepare for step 7: `panel.admin` adds the test student live.
2. Open `http://127.0.0.1:8000/` in a normal window. It shows the welcome page; each step starts with **Log in** in the top bar, and **Log out** returns to the welcome page.

**Why two admins:** demo accounts are never written to the audit log, by design, so that test clicks don't pollute the real history. `panel.admin` is a real account, which is how step 7 can show a genuine audit entry.

**Reset between rehearsals:** steps 2, 3, 5 and 7 change data. Run `purge_demo` then `seed_demo` again. Tolu Ade (step 7) is a real account, so `purge_demo` leaves it: before the next rehearsal, deactivate Tolu from System administration → Student accounts, or use a different student identification number and email each time.

**What the seed contains:**
- One faculty with two departments, Computer Science and Software Engineering.
- In each department, a coordinator, a Head of Department and three supervisors, one per approval method:

  | Approval method | Computer Science | Software Engineering |
  |---|---|---|
  | topic only | `demo.danjuma` | `demo.yusuf` |
  | literature review | `demo.okoro` | `demo.nwosu` |
  | working project | `demo.eze` | `demo.lawal` |

- 21 projects across every stage, including 4 archived projects with documented gaps. Only two of those students are graduated, which shows that completion and graduation are separate.
- "Campus Shuttle Tracker" (archived, 2024) overlaps the running "Campus Shuttle Delay Tracker", so the similar-topic panel has a match to show.
- Health score bands: `demo.amina` at risk (75), `demo.yemi` and `demo.sadiq` watch (50 and 39), `demo.chinedu` on track (20). Their history, milestones and meetings are back-dated for this.

---

## Step 1 (0:00–1:00): Student, `demo.adaeze`: the decision history nobody can rewrite

1. Log in with **`adaeze@bazeuniversity.edu.ng`**: everyone, students and staff, logs in with their Baze email.
2. The student portal opens. Point at the stage track: "Approved by the department".
3. Click **View progress** to open the Project workflow.
4. Scroll to **History**: every stage change, with who made it and when.
5. Scroll to **Approval decisions**. There are three entries:
   - Dr Okoro **declined** the first idea, "Timetable Clash Checker for the Whole University", with his reason.
   - He then **accepted with changes** the narrowed topic.
   - The department logged the form.
6. **Say:** "The form itself is replaced when a student resubmits, but this list is append-only. The rejection and its reason stay on record."

**If it breaks:**
- If login by identification number fails, use `demo.adaeze`.
- If the page errors, run `manage.py test apps.accounts.tests.SeedAndPurgeTests.test_seed_includes_a_visible_append_only_decision_history` and show that it passes.

## Step 2 (1:00–2:00): Supervisor, `demo.danjuma`: accept a proposal under his own rules

1. Log out, then log in as `demo.danjuma`.
2. Click **Review criteria** in the top bar. His method is "Topic, aim and methodology". Mention that Dr Okoro requires a literature review and Dr Eze a working prototype: each supervisor sets their own (R-13).
3. Click **Portal home**. In his student list, click **Hostel Maintenance Request Tracker** (Kemi Adebayo, stage "Topic proposed").
4. On the workflow page:
   - set **Decision** to "Accepted as proposed";
   - type a short comment and his name as it appears on the form;
   - keep today's date;
   - click **Save workflow step**.
5. The stage changes to **Supervisor accepted**, and a new line appears under History and Approval decisions.

**If it breaks:**
- If the form isn't shown, the project has already moved on (the data wasn't reset). Open **Microservice Template for Student Projects** as `demo.lawal` instead: also a pending proposal, under the "working project" method.
- Otherwise, reseed.

## Step 3 (2:00–3:00): Coordinator, `demo.coordinator`: log the form, allocate a student

1. Log in as `demo.coordinator`.
2. Click **Approval register**. Kemi's project now shows "Supervisor accepted". Click **Review project workflow**.
3. Enter a note (for example "Filed in the register"), keep today's date, then click **Save workflow step**. The stage changes to **Approved by the department**.
4. Click **Student allocation**. Find **Lecture Attendance with QR Codes** (Musa Garba, "Unassigned").
5. Choose **K. Danjuma**, give the reason "Topic fits Mr Danjuma", then click **Save assignment**. The card shows the new supervisor and the change is kept in the history.
6. **Say:** "A coordinator works across their faculty; a supervisor or Head of Department given allocation rights stays within their department. The system enforces one current supervisor per project in the database, on MySQL as well."

**If it breaks:**
- If Kemi isn't listed, use **Accessibility Checker for Course Pages**. It is in Software Engineering, so log in as `demo.se.coordinator`.
- If allocation fails, show the existing history on **Exam Seating Allocation Tool** in the repository (it was reassigned once).

## Step 4 (3:00–4:00): Supervisor, `demo.okoro`: meeting records both sides can rely on

1. Log in as `demo.okoro`.
2. On the portal, find **Campus Event Notification App** (Chinedu Okafor) and click **Meeting log**.
3. The log shows two held meetings and one upcoming. Click **View record** on the most recent held meeting (about a week ago).
4. Show:
   - what was discussed and the **Corrective action**, in the supervisor's words;
   - the student's **dispute**: "I sent the survey design by email…";
   - the record's **Version history**.
5. **Say:** "Meeting records are visible only to the student, their supervisor, and the department's coordinator and Head of Department (R-33). Another supervisor in the same department gets a 'Not allowed' page."

**If it breaks:**
- If the meeting log is empty, the seed didn't run its supervision records. Reseed.
- To prove the privacy rule instead, log in as `demo.danjuma`, paste the meeting record's web address, and show the 403 page.

## Step 5 (4:00–5:00): Head of Department, `demo.hod`: sign off and archive

1. Log in as `demo.hod`.
2. The portal's sign-off queue lists **Cafeteria Queue Predictor** (Ngozi Chukwu, "Defended"). Click it.
3. On the workflow page:
   - The **Gap summary** is already filled in from the project: "Only lunch-time data was available…"
   - Add a completion note.
   - **Leave "Graduation verified" unticked.**
   - Click **Save workflow step**.
4. You land on the archived record. Point at **Documented gap** and at **Graduation: Not yet verified (project completed)**.
5. **Say:** "Only the Head of Department can archive. A sign-off needs a documented gap or an explicit 'no gap' tick. Finishing the project is not the same as graduating, so graduation is shown separately, and the project is in the repository straight away."

**If it breaks:**
- If the queue is empty (Ngozi was already signed off), use **Requirements Traceability Tool** as `demo.se.hod`.
- If the save is refused with "Record the documented gap…", the gap box was cleared. Type a gap or tick "no documented gap".

## Step 6 (5:00–6:00): Current student, `demo.chinedu`: find past work, acknowledge a notice

1. Log in with the **email** `chinedu@bazeuniversity.edu.ng`.
2. Click **Completed projects** and search for **`queue`**. Ngozi's project, archived one minute ago, is listed. Open it:
   - the documented gap is there to "continue";
   - **Project abstract** can be downloaded;
   - the staff-only final report is not offered to a student.
3. Search for **`Exam Seating`** and open it: graduated student, verified graduation year, **Earlier supervisor** shown.
4. Click **Notifications**. The notice **Venue change for Thursday's meeting** asks for acknowledgement. Click **Acknowledge notice**.
5. **Say:** "The system records when each student first saw and acknowledged a notice, so 'I never got the message' can be checked."

**If it breaks:**
- If search shows nothing, clear the filters and use the year filter, or open **Student Wellbeing Check-in Chatbot**, which is always archived in the seed.
- If the download fails, say files are served only through a permission check, then show the file list on the page.

## Step 7 (6:00–7:00): Administrator, `panel.admin`: add a student, read the audit log

1. Log in as `panel.admin@bazeuniversity.edu.ng`, the real admin from the setup.
2. Click **System administration** → **Add student account**. Enter Tolu Ade, `tolu.ade@bazeuniversity.edu.ng`, student identification number `BU/23A/CS/5001`, programme "Computer Science Bachelor of Science", status "Current final-year student". Click **Create student account**; a temporary password is shown once.
3. **Say:** "Students can't create their own accounts. The coordinator or the administrator adds each final-year student after checking they're ready, so only the right students get in. The student must choose their own password at first sign-in."
4. Click **Audit log**. The newest entry is "Student account created", with who did it and when.
5. **Say:**
   - "The audit log is admin-only and append-only: the database itself refuses UPDATE and DELETE on it.
   - Demo accounts are deliberately left out of it, which is why everything we clicked as `demo.*` isn't listed.
   - Real data replaces the demo with one command, `purge_demo`, plus a CSV import of past projects."

**If it breaks:**
- If Tolu already exists from a rehearsal, use another identification number and email (for example `BU/23A/CS/5002`, `tolu.ade2@bazeuniversity.edu.ng`).
- If `panel.admin` doesn't exist, use `demo.admin`. Adding the student works, but explain that it won't appear in the audit log because demo accounts are excluded.

---

## If the panel asks for more (not timed)

- **The coordinator uploads the final report:** as `demo.coordinator`, open a Computer Science project that is in progress, submitted or defended, then **Project workflow → Upload final report**. The file is listed under **Project files** with the coordinator's name, and the Head of Department's sign-off still archives it.
- **Semesters (26A, 26B, 26C):** the seed puts the running projects in 26A and 26B. As `demo.coordinator`, open a project's workflow page, type `26C` in **Semester** and click **Save semester**: 26C is added on first use. Then **Deadlines → Add a deadline** with semester `26C`: it appears on that project and nowhere else. In **Running topics**, type `26A` in **Semester** to filter.
- **Searching by year:** in the repository, click **Year**: a year grid opens, with years that have projects clickable.

## Timing

| Step | Role | Account | Minutes |
|---|---|---|---|
| 1 | Student | `demo.adaeze` (identification number `BU/22A/CS/4041`) | 0:00–1:00 |
| 2 | Supervisor | `demo.danjuma` | 1:00–2:00 |
| 3 | Coordinator | `demo.coordinator` | 2:00–3:00 |
| 4 | Supervisor | `demo.okoro` | 3:00–4:00 |
| 5 | Head of Department | `demo.hod` | 4:00–5:00 |
| 6 | Student | `chinedu@bazeuniversity.edu.ng` | 5:00–6:00 |
| 7 | Administrator | `panel.admin` | 6:00–7:00 |

**If the whole app is down:** run `manage.py test apps` on SQLite (about 30 seconds) and show the passing suite, then walk through `docs/diagrams/` for the state machine and the sign-off sequence. Known limits are in `docs/known_limits.md`. Mention them before the panel asks.
