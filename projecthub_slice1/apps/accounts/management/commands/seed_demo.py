"""Create a demo department story (all rows flagged is_demo=True). Safe to run more than once.

The story: one faculty, two departments, six supervisors with different approval methods, and
twenty student projects spread across every stage, from an unassigned proposal to three archived
projects with documented gaps. Each project is moved forward through the same services the web
pages use (proposal, supervisor decision, coordinator log, stage changes, HOD sign-off), so its
status history, approval form and decision history are real, not typed in.

Demo activity is not written to the audit log (apps/audit/services.py skips is_demo rows).
Remove everything with `python manage.py purge_demo`.
"""
from datetime import date, timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, SupervisorProfile, User
from apps.projects.models import (
    DocumentType,
    Project,
    ProjectDocument,
    ProjectStage,
    ProjectStatusEvent,
    SupervisorDecision,
)
from apps.projects.services import (
    assign_project_supervisor,
    log_approved_form,
    record_supervisor_decision,
    record_transition,
    sign_off_completion,
    submit_proposal,
)
from apps.supervision.models import (
    Announcement,
    MeetingRecordEdit,
    SharedResource,
    SupervisionMeeting,
    SupervisorAvailability,
)

FACULTY = "Faculty of Computing (demo)"
CS = "Computer Science"
SE = "Software Engineering"
STRUCTURE = {CS: ("CS", ["BSc", "MSc"]), SE: ("SE", ["BSc"])}

TOPIC_ONLY, LITERATURE_REVIEW, WORKING_PROJECT = "topic_only", "literature_review", "working_project"

# username, first, last, role, department, title, approval method, extra criteria
STAFF = [
    ("demo.admin", "Demo", "Admin", Role.ADMIN, CS, "", None, ""),
    ("demo.hod", "Halima", "Abubakar", Role.HOD, CS, "Prof.", None, ""),
    ("demo.coordinator", "Emeka", "Obi", Role.COORDINATOR, CS, "Dr.", None, ""),
    ("demo.se.hod", "Bola", "Adeyemi", Role.HOD, SE, "Prof.", None, ""),
    ("demo.se.coordinator", "Zainab", "Ibrahim", Role.COORDINATOR, SE, "Dr.", None, ""),
    ("demo.okoro", "A.", "Okoro", Role.SUPERVISOR, CS, "Dr.", LITERATURE_REVIEW,
     "At least ten sources from the last five years, and a clearly stated research gap."),
    ("demo.danjuma", "K.", "Danjuma", Role.SUPERVISOR, CS, "Mr.", TOPIC_ONLY, ""),
    ("demo.eze", "C.", "Eze", Role.SUPERVISOR, CS, "Dr.", WORKING_PROJECT,
     "Show a clickable prototype of the main screen before I accept."),
    ("demo.yusuf", "B.", "Yusuf", Role.SUPERVISOR, SE, "Mrs.", TOPIC_ONLY, ""),
    ("demo.nwosu", "I.", "Nwosu", Role.SUPERVISOR, SE, "Dr.", LITERATURE_REVIEW,
     "Compare at least three existing tools in the literature review."),
    ("demo.lawal", "T.", "Lawal", Role.SUPERVISOR, SE, "Mr.", WORKING_PROJECT,
     "A running build in a public repository."),
]
COORDINATOR = {CS: "demo.coordinator", SE: "demo.se.coordinator"}
HOD = {CS: "demo.hod", SE: "demo.se.hod"}

# username, first, last, student number, department
STUDENTS = [
    ("demo.amina", "Amina", "Bello", "BU/22/CS/4012", CS),
    ("demo.chinedu", "Chinedu", "Okafor", "BU/22/CS/3988", CS),
    ("demo.ibrahim", "Ibrahim", "Musa", "BU/22/CS/3901", CS),
    ("demo.tunde", "Tunde", "Bakare", "BU/21/CS/3850", CS),
    ("demo.kemi", "Kemi", "Adebayo", "BU/22/CS/4020", CS),
    ("demo.musa", "Musa", "Garba", "BU/22/CS/4033", CS),
    ("demo.adaeze", "Adaeze", "Nnamdi", "BU/22/CS/4041", CS),
    ("demo.sadiq", "Sadiq", "Umar", "BU/22/CS/4057", CS),
    ("demo.ngozi", "Ngozi", "Chukwu", "BU/22/CS/4068", CS),
    ("demo.femi", "Femi", "Ojo", "BU/22/CS/4075", CS),
    ("demo.fatima", "Fatima", "Sule", "BU/22/SE/4101", SE),
    ("demo.grace", "Grace", "Eze", "BU/21/SE/3877", SE),
    ("demo.halima", "Halima", "Bala", "BU/22/SE/4112", SE),
    ("demo.obinna", "Obinna", "Kalu", "BU/22/SE/4125", SE),
    ("demo.zainab", "Zainab", "Aliyu", "BU/22/SE/4133", SE),
    ("demo.yemi", "Yemi", "Alade", "BU/22/SE/4140", SE),
    ("demo.aisha", "Aisha", "Danladi", "BU/22/SE/4152", SE),
    ("demo.kunle", "Kunle", "Afolabi", "BU/22/SE/4160", SE),
    ("demo.bisi", "Bisi", "Akande", "BU/22/SE/4171", SE),
    ("demo.ikenna", "Ikenna", "Obi", "BU/22/SE/4188", SE),
]

# Target stages. "proposed" variants all end at PROPOSED; "history" ends APPROVED with a
# declined first proposal kept in the decision history.
UNASSIGNED, PENDING, DECLINED = "proposed_unassigned", "proposed_pending", "proposed_declined"
ACCEPTED, APPROVED, HISTORY = "accepted", "approved", "approved_history"
IN_PROGRESS, SUBMITTED, DEFENDED, ARCHIVED = "in_progress", "submitted", "defended", "archived"
ORDER = [PENDING, ACCEPTED, APPROVED, IN_PROGRESS, SUBMITTED, DEFENDED, ARCHIVED]

# student, title, description, keywords, supervisor, target, extras
PROJECTS = [
    ("demo.amina", "Mobile Money Fraud Alerts for Small Traders",
     "A lightweight service that helps small traders spot suspicious mobile-money activity.",
     "fintech, fraud detection, mobile money", "demo.okoro", IN_PROGRESS, {}),
    ("demo.chinedu", "Campus Event Notification App",
     "A mobile-first platform for sharing verified campus events and schedule changes.",
     "mobile, notifications, events", "demo.okoro", IN_PROGRESS, {}),
    ("demo.ibrahim", "Campus Shuttle Delay Tracker",
     "A student-facing tool for reporting and reviewing campus shuttle delays.",
     "transport, crowdsourcing", "demo.danjuma", ACCEPTED, {}),
    ("demo.tunde", "Exam Seating Allocation Tool",
     "A decision-support tool for allocating examination seats across halls.",
     "optimisation, scheduling", "demo.eze", ARCHIVED,
     {"previous": "demo.danjuma", "graduated": True, "signed": "2025-07-10",
      "gap": "The allocation rules could be extended to accessibility needs and late registration changes."}),
    ("demo.kemi", "Hostel Maintenance Request Tracker",
     "A web app for logging and following up hostel maintenance requests.",
     "facilities, ticketing", "demo.danjuma", PENDING, {}),
    ("demo.musa", "Lecture Attendance with QR Codes",
     "Recording lecture attendance by scanning a code shown in class.",
     "attendance, QR", None, UNASSIGNED, {}),
    ("demo.adaeze", "Course Registration Clash Detector",
     "Detects timetable clashes when students register for courses, before registration closes.",
     "timetabling, constraint checking", "demo.okoro", HISTORY,
     {"first_title": "Timetable Clash Checker for the Whole University",
      "declined": "The scope is too broad for one student. Narrow it to course registration and "
                  "review the existing clash-detection tools first.",
      "accepted": "Accepted with changes: evaluate with one semester of real registration data."}),
    ("demo.sadiq", "Offline-first Library Kiosk",
     "A library kiosk that keeps working during network outages and syncs later.",
     "offline-first, sync", "demo.eze", SUBMITTED, {}),
    ("demo.ngozi", "Cafeteria Queue Predictor",
     "Predicts cafeteria queue length from historical sales to suggest quieter times.",
     "forecasting, data analysis", "demo.danjuma", DEFENDED,
     {"gap_hint": "Only lunch-time data was available; breakfast and dinner patterns are untested."}),
    ("demo.femi", "Student Wellbeing Check-in Chatbot",
     "A chatbot that offers weekly wellbeing check-ins and points students to campus support.",
     "chatbot, wellbeing", "demo.okoro", ARCHIVED,
     {"graduated": False, "signed": None,
      "gap": "The chatbot was tested with 30 volunteers; a longer study with the counselling unit is needed."}),
    ("demo.fatima", "Library Catalogue Extension: Reservations",
     "A library catalogue extension for reserving books and checking collection status.",
     "library, reservations", "demo.yusuf", DECLINED,
     {"declined": "Please explain how this differs from the reservation feature the library already has."}),
    ("demo.grace", "Student Complaint Routing Portal",
     "A web portal that routes student service complaints to the right unit.",
     "workflow, routing", "demo.yusuf", ARCHIVED,
     {"graduated": False, "signed": "2025-07-12",
      "gap": "The evaluation covered one department; future work could test routing across all faculties."}),
    ("demo.halima", "Lab Equipment Booking System",
     "Booking shared lab equipment with clash checks and reminders.",
     "booking, scheduling", "demo.nwosu", ACCEPTED, {}),
    ("demo.obinna", "Code Review Assistant for Student Teams",
     "Suggests reviewers and flags risky changes in student team repositories.",
     "code review, developer tools", "demo.lawal", APPROVED, {}),
    ("demo.zainab", "Internship Logbook App",
     "A digital logbook for SIWES internships with supervisor sign-off.",
     "internship, logbook", "demo.yusuf", APPROVED, {}),
    ("demo.yemi", "CI Pipeline Dashboard for Coursework",
     "Shows build and test status for every coursework repository in one place.",
     "continuous integration, dashboards", "demo.lawal", IN_PROGRESS, {}),
    ("demo.aisha", "Bug Bounty Platform for Campus Apps",
     "A platform where students report security bugs in university apps responsibly.",
     "security, bug bounty", "demo.nwosu", SUBMITTED, {}),
    ("demo.kunle", "Requirements Traceability Tool",
     "Links requirements to code and tests so coverage gaps are visible.",
     "requirements, traceability", "demo.yusuf", DEFENDED, {}),
    ("demo.bisi", "Accessibility Checker for Course Pages",
     "Checks course web pages against common accessibility guidelines.",
     "accessibility, WCAG", "demo.nwosu", ACCEPTED, {}),
    ("demo.ikenna", "Microservice Template for Student Projects",
     "A starter template with logging, tests and deployment for student microservices.",
     "microservices, templates", "demo.lawal", PENDING, {}),
]


class Command(BaseCommand):
    help = "Create the demo department story (everything flagged is_demo)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="ChangeMe123!", help="Password for every demo account")
        parser.add_argument("--force", action="store_true", help="Allow running when DEBUG is False")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError("Refusing to create demo accounts when DEBUG is False. Use --force only if you are sure.")
        self.today = timezone.localdate()

        departments, programmes = self._structure()
        self.users = {}
        for username, first, last, role, dep, title, method, criteria in STAFF:
            user = self._user(username, first, last, role, departments[dep], opts["password"])
            if role == Role.COORDINATOR and not user.can_assign_supervisors:
                user.can_assign_supervisors = True
                user.save(update_fields=["can_assign_supervisors"])
            if role == Role.ADMIN and not user.is_staff:
                user.is_staff = True  # lets the demo admin open /admin/
                user.save(update_fields=["is_staff"])
            if method:
                SupervisorProfile.objects.get_or_create(
                    user=user,
                    defaults={"title": title, "approval_method": method, "approval_criteria": criteria},
                )
        for username, first, last, number, dep in STUDENTS:
            user = self._user(username, first, last, Role.STUDENT, departments[dep], opts["password"])
            StudentProfile.objects.get_or_create(
                user=user,
                defaults={"student_number": number, "programme": programmes[dep], "enrolment_year": 2022},
            )

        built = 0
        for spec in PROJECTS:
            if not Project.objects.filter(student=self.users[spec[0]], is_demo=True).exists():
                self._build_project(*spec)
                built += 1
        if built:
            self._supervision_records()

        self.stdout.write(self.style.SUCCESS(f"Demo data ready ({built} new projects)."))
        self.stdout.write(f"Log in as any demo.* user. Password: {opts['password']}")
        self.stdout.write(self.style.WARNING("Demo accounts are for development only. Remove them with: python manage.py purge_demo"))

    # --- structure and people ------------------------------------------------------------------

    def _structure(self):
        faculty, _ = Faculty.objects.get_or_create(name=FACULTY, defaults={"code": "FOC", "is_demo": True})
        departments, programmes = {}, {}
        for name, (code, degrees) in STRUCTURE.items():
            department, _ = Department.objects.get_or_create(
                faculty=faculty, name=name, defaults={"code": code, "is_demo": True}
            )
            departments[name] = department
            for degree in degrees:
                programme, _ = Programme.objects.get_or_create(
                    department=department, name=name, degree_type=degree, defaults={"is_demo": True}
                )
                programmes.setdefault(name, programme)  # students are on the first (BSc) programme
        return departments, programmes

    def _user(self, username, first, last, role, department, password):
        email = f"{username.removeprefix('demo.')}@bazeuniversity.edu.ng"
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": first,
                "last_name": last,
                "email": email,
                "role": role,
                "department": department,
                "is_demo": True,
            },
        )
        if created:
            user.set_password(password)
            user.save()
        elif not user.email:
            user.email = email
            user.save(update_fields=["email"])
        self.users[username] = user
        return user

    # --- projects -------------------------------------------------------------------------------

    def _fresh(self, project):
        return Project.objects.get(pk=project.pk)

    def _days_ago(self, days):
        return self.today - timedelta(days=days)

    def _build_project(self, student_name, title, description, keywords, supervisor_name, target, extras):
        student = self.users[student_name]
        department = student.department
        coordinator = self.users[COORDINATOR[department.name]]
        hod = self.users[HOD[department.name]]
        supervisor = self.users.get(supervisor_name)

        # What the "Start my project" page does.
        project = Project.objects.create(
            student=student, title=extras.get("first_title", title), description=description, keywords=keywords,
            department=department, programme=student.student_profile.programme, is_demo=True,
        )
        ProjectStatusEvent.objects.create(
            project=project, from_stage="", to_stage=ProjectStage.PROPOSED, actor=student,
            note="Student created the initial project record.",
        )
        if supervisor is None:
            return
        if extras.get("previous"):
            assign_project_supervisor(
                project.pk, self.users[extras["previous"]], assigned_by=coordinator,
                change_reason="Initial allocation by the department.",
            )
            assign_project_supervisor(
                project.pk, supervisor, assigned_by=coordinator,
                change_reason="Reassigned: the first supervisor went on sabbatical.",
            )
        else:
            assign_project_supervisor(project.pk, supervisor, assigned_by=coordinator, change_reason="Departmental allocation.")

        method = supervisor.supervisor_profile.approval_method
        self._propose(project, student, extras.get("first_title", title), method, days_ago=60)
        if target == PENDING:
            return
        if target in (DECLINED, HISTORY):
            self._decide(project, supervisor, SupervisorDecision.REJECTED, extras["declined"], days_ago=55)
            if target == DECLINED:
                return
            self._propose(project, student, title, method, days_ago=50)
            self._decide(project, supervisor, SupervisorDecision.ACCEPTED_WITH_CHANGES, extras["accepted"], days_ago=48)
            target = APPROVED
        else:
            self._decide(project, supervisor, SupervisorDecision.ACCEPTED, "Good topic; proceed.", days_ago=55)

        stage_reached = ORDER.index(target)
        if stage_reached >= ORDER.index(APPROVED):
            log_approved_form(
                self._fresh(project), coordinator=coordinator,
                notes="Signed form filed in the departmental register.", logged_on=self._days_ago(45),
            )
        if stage_reached >= ORDER.index(IN_PROGRESS):
            record_transition(project, ProjectStage.IN_PROGRESS, actor=supervisor, note="Work started.",
                              when=self._days_ago(44))
        if stage_reached >= ORDER.index(SUBMITTED):
            self._attach_files(project, student)
            record_transition(project, ProjectStage.SUBMITTED, actor=student, note="Final report submitted.",
                              when=self._days_ago(10))
        if stage_reached >= ORDER.index(DEFENDED):
            record_transition(project, ProjectStage.DEFENDED, actor=coordinator, note="Defended before the panel.",
                              when=self._days_ago(5))
            if extras.get("gap_hint"):
                Project.objects.filter(pk=project.pk).update(gap_summary=extras["gap_hint"])
        if target == ARCHIVED:
            signed = extras.get("signed")
            signed_on = date.fromisoformat(signed) if signed else self._days_ago(2)
            sign_off_completion(
                self._fresh(project), hod, signed_on=signed_on,
                completion_note="Corrections checked and the final copy received.",
                gap_summary=extras["gap"],
                graduation_verified=extras["graduated"],
                graduation_year=signed_on.year if extras["graduated"] else None,
            )

    def _propose(self, project, student, title, method, days_ago):
        evidence = {}
        if method == LITERATURE_REVIEW:
            evidence = {
                "literature_review": "Reviewed twelve recent papers and three existing tools.",
                "research_gap": "None of the tools reviewed handle the Baze registration rules.",
            }
        elif method == WORKING_PROJECT:
            evidence = {"working_project_demonstration": "Prototype of the main screen shown in the meeting."}
        submit_proposal(
            self._fresh(project), proposed_title=title,
            problem_statement="Students and staff lose time to this problem every semester.",
            objectives="Build, deploy and evaluate a working tool.",
            methodology="Requirements interviews, iterative development, then a user evaluation.",
            tools_and_technologies="Python, Django, MySQL",
            student_name_on_form=student.get_full_name(), signed_on=self._days_ago(days_ago), **evidence,
        )

    def _decide(self, project, supervisor, decision, comments, days_ago):
        record_supervisor_decision(
            self._fresh(project), supervisor=supervisor, decision=decision, comments=comments,
            name_on_form=supervisor.get_full_name(), signed_on=self._days_ago(days_ago),
        )

    def _attach_files(self, project, student):
        """A staff-only final report (needed to submit) and a public abstract for the repository."""
        slug = student.username.removeprefix("demo.")
        for title, kind, visibility in (
            ("Final report", DocumentType.REPORT, ProjectDocument.Visibility.STAFF_ONLY),
            ("Project abstract", DocumentType.OTHER, ProjectDocument.Visibility.BAZE_USERS),
        ):
            document = ProjectDocument(
                project=project, title=title, document_type=kind, visibility=visibility,
                uploaded_by=student, is_demo=True,
            )
            content = f"%PDF-1.4\n% Synthetic demo file: {title} for {project.title}\n".encode()
            document.file.save(f"demo-{slug}-{kind}.pdf", ContentFile(content), save=False)
            document.save()

    # --- meetings, notices, resources ------------------------------------------------------------

    def _supervision_records(self):
        okoro, lawal, yusuf = self.users["demo.okoro"], self.users["demo.lawal"], self.users["demo.yusuf"]
        chinedu = Project.objects.get(student=self.users["demo.chinedu"], is_demo=True)
        yemi = Project.objects.get(student=self.users["demo.yemi"], is_demo=True)
        now = timezone.now()

        held = self._meeting(chinedu, okoro, now - timedelta(days=21), "held",
                             discussion="Agreed the core features and the evaluation plan.",
                             corrective_action="Draft chapter one before the next meeting.")
        held.student_confirmed_at = held.supervisor_confirmed_at = now - timedelta(days=20)
        held.save(update_fields=["student_confirmed_at", "supervisor_confirmed_at"])
        disputed = self._meeting(chinedu, okoro, now - timedelta(days=7), "held",
                                 discussion="Reviewed chapter one; the methodology section is thin.",
                                 corrective_action="Expand the methodology with the survey design.")
        disputed.student_disputed_at = now - timedelta(days=6)
        disputed.student_comment = "I sent the survey design by email on the Monday before this meeting."
        disputed.save(update_fields=["student_disputed_at", "student_comment"])
        self._meeting(chinedu, okoro, now + timedelta(days=3), "scheduled", agenda="Chapter two progress.")
        self._meeting(yemi, lawal, now - timedelta(days=14), "held",
                      discussion="Demo of the first dashboard build.", corrective_action="Add failing-test alerts.")
        self._meeting(yemi, lawal, now - timedelta(days=4), "missed")

        Announcement.objects.create(
            author=okoro, project=chinedu, department=chinedu.department, requires_acknowledgement=True,
            title="Venue change for Thursday's meeting",
            body="Thursday's meeting moves to Room B12 at the same time.",
        )
        Announcement.objects.create(
            author=yusuf, department=yemi.department, is_pinned=True,
            title="Software Engineering defence schedule",
            body="Defences run in the last week of the semester. Book a slot with the coordinator.",
        )
        guide = SharedResource.objects.create(
            author=okoro, department=okoro.department, title="Literature review checklist",
            description="Use this before sending me your chapter two.", url="https://example.com/literature-checklist",
        )
        guide.projects.set(Project.objects.filter(supervisor=okoro, archived=False, is_demo=True))
        SupervisorAvailability.objects.create(
            supervisor=okoro, weekday=1, start_time="10:00", end_time="12:00", venue="Room B12",
        )

    def _meeting(self, project, supervisor, when, status, **notes):
        meeting = SupervisionMeeting.objects.create(
            project=project, scheduled_for=when, duration_minutes=60, venue="Room B12", status=status,
            scheduled_by=supervisor, recorded_by=supervisor, **notes,
        )
        MeetingRecordEdit.objects.create(meeting=meeting, edited_by=supervisor, changes={"created": {"to": "Meeting scheduled"}})
        return meeting
