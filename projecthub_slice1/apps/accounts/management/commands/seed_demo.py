"""Create demo data (all rows flagged is_demo=True). Safe to run more than once."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import Department, Faculty, Programme
from apps.accounts.models import Role, StudentProfile, SupervisorProfile, User
from apps.projects.models import ArchivedProject, Project, ProjectStage
from apps.projects.services import assign_project_supervisor

COMPUTING = "Faculty of Computing (demo)"
LAW = "Faculty of Law (demo)"

STRUCTURE = {
    COMPUTING: {"Computer Science": ["BSc", "MSc"], "Software Engineering": ["BSc", "MSc"]},
    LAW: {"Private Law": ["LLB", "LLM"]},
}

# username, first, last, role, department, title
STAFF = [
    ("demo.admin", "Demo", "Admin", Role.ADMIN, "Computer Science", ""),
    ("demo.hod", "Demo", "Head", Role.HOD, "Computer Science", "Prof."),
    ("demo.coordinator", "Demo", "Coordinator", Role.COORDINATOR, "Computer Science", "Dr."),
    ("demo.okoro", "A.", "Okoro", Role.SUPERVISOR, "Computer Science", "Dr."),
    ("demo.yusuf", "B.", "Yusuf", Role.SUPERVISOR, "Software Engineering", "Mrs."),
    ("demo.danjuma", "K.", "Danjuma", Role.SUPERVISOR, "Computer Science", "Mr."),
]

# username, first, last, student number, department, degree
STUDENTS = [
    ("demo.amina", "Amina", "Bello", "BU/22/CS/4012", "Computer Science", "BSc"),
    ("demo.chinedu", "Chinedu", "Okafor", "BU/22/CS/3988", "Computer Science", "BSc"),
    ("demo.fatima", "Fatima", "Sule", "BU/22/SE/4101", "Software Engineering", "BSc"),
    ("demo.ibrahim", "Ibrahim", "Musa", "BU/22/CS/3901", "Computer Science", "BSc"),
    ("demo.grace", "Grace", "Eze", "BU/22/SE/3877", "Software Engineering", "BSc"),
    ("demo.tunde", "Tunde", "Bakare", "BU/22/CS/3850", "Computer Science", "BSc"),
]

CURRENT_PROJECTS = [
    (
        "demo.amina",
        "Mobile Money Fraud Alerts for Small Traders",
        "Designing a lightweight service that helps small traders identify suspicious mobile-money activity.",
        "3",
        "demo.okoro",
    ),
    (
        "demo.chinedu",
        "Campus Event Notification App",
        "A mobile-first platform for sharing verified campus events and schedule updates.",
        "3",
        "demo.okoro",
    ),
    (
        "demo.fatima",
        "Library Catalogue Extension: Reservations",
        "A library catalogue extension for reserving books and checking collection status.",
        "0",
        "demo.yusuf",
    ),
    (
        "demo.ibrahim",
        "Campus Shuttle Delay Tracker",
        "A student-facing tool for reporting and reviewing campus shuttle delays.",
        "1",
        "demo.danjuma",
    ),
]

ARCHIVED_PROJECTS = [
    (
        "demo.grace",
        "Student Complaint Routing Portal",
        "A web portal for routing student service complaints to the appropriate unit.",
        "2025",
        "demo.yusuf",
        "The evaluation covered one department; future work could test the workflow across additional faculties.",
        "2025",
        "demo.okoro",
    ),
    (
        "demo.tunde",
        "Exam Seating Allocation Tool",
        "A decision-support tool for allocating examination seats.",
        "2024",
        "demo.okoro",
        "The current allocation rules could be extended to support accessibility and late registration changes.",
        "2024",
        "demo.danjuma",
    ),
]


class Command(BaseCommand):
    help = "Create demo faculties, departments, programmes and users (flagged is_demo)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="ChangeMe123!", help="Password for every demo account")
        parser.add_argument("--force", action="store_true", help="Allow running when DEBUG is False")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError("Refusing to create demo accounts when DEBUG is False. Use --force only if you are sure.")

        depts = {}
        for fac_name, deps in STRUCTURE.items():
            fac, _ = Faculty.objects.get_or_create(name=fac_name, defaults={"is_demo": True})
            for dep_name, degrees in deps.items():
                dep, _ = Department.objects.get_or_create(faculty=fac, name=dep_name, defaults={"is_demo": True})
                depts[dep_name] = dep
                for degree in degrees:
                    Programme.objects.get_or_create(
                        department=dep, name=dep_name, degree_type=degree, defaults={"is_demo": True}
                    )

        for username, first, last, role, dep_name, title in STAFF:
            user = self._user(username, first, last, role, depts[dep_name], opts["password"])
            if username == "demo.coordinator" and not user.can_assign_supervisors:
                user.can_assign_supervisors = True
                user.save(update_fields=["can_assign_supervisors"])
            if role == Role.ADMIN:
                user.is_staff = True  # lets the demo admin open /admin/
                user.save(update_fields=["is_staff"])
            if role == Role.SUPERVISOR:
                SupervisorProfile.objects.get_or_create(user=user, defaults={"title": title})

        student_users = {}
        for username, first, last, number, dep_name, degree in STUDENTS:
            user = self._user(username, first, last, Role.STUDENT, depts[dep_name], opts["password"])
            student_users[username] = user
            programme = Programme.objects.get(department=depts[dep_name], name=dep_name, degree_type=degree)
            StudentProfile.objects.get_or_create(
                user=user, defaults={"student_number": number, "programme": programme, "enrolment_year": 2022}
            )

        staff_users = {username: User.objects.get(username=username) for username, *_ in STAFF}
        for username, title, description, stage, supervisor_username in CURRENT_PROJECTS:
            student = student_users[username]
            project, _ = Project.objects.update_or_create(
                student=student,
                is_demo=True,
                defaults={
                    "title": title,
                    "description": description,
                    "department": student.department,
                    "programme": student.student_profile.programme,
                    "supervisor": staff_users[supervisor_username],
                    "stage": stage,
                },
            )
            assign_project_supervisor(
                project_id=project.pk,
                supervisor=staff_users[supervisor_username],
                assigned_by=None,
                change_reason="Synthetic demo record initial assignment.",
            )

        for username, title, description, year, supervisor_username, gap, graduation_year, previous_supervisor_username in ARCHIVED_PROJECTS:
            student = student_users[username]
            archived_project, _ = ArchivedProject.objects.update_or_create(
                student=student,
                title=title,
                is_demo=True,
                defaults={
                    "description": description,
                    "year": year,
                    "department": student.department,
                    "programme": student.student_profile.programme,
                    "supervisor": staff_users[supervisor_username],
                    "gap_summary": gap,
                },
            )
            archived_project.previous_supervisors.add(staff_users[previous_supervisor_username])
            profile = student.student_profile
            profile.student_status = StudentProfile.Status.GRADUATED
            profile.graduation_year = graduation_year
            profile.save(update_fields=["student_status", "graduation_year"])

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"Log in as any demo.* user. Password: {opts['password']}")
        self.stdout.write(self.style.WARNING("Demo accounts are for development only. Remove them with: python manage.py purge_demo"))

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
        return user
