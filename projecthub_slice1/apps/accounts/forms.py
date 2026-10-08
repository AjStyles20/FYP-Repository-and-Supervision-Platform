import secrets

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import Department, Programme

from .models import STAFF_ROLES, Role, StudentProfile, SupervisorProfile, User

BAZE_EMAIL_DOMAIN = "@bazeuniversity.edu.ng"


class ProjectAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Baze email, student ID, or staff username",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )

    def clean(self):
        identifier = self.cleaned_data.get("username")
        if identifier:
            account = User.objects.filter(email__iexact=identifier).first()
            if account is None:
                profile = (
                    StudentProfile.objects.filter(student_number__iexact=identifier)
                    .select_related("user")
                    .first()
                )
                account = profile.user if profile else None
            if account:
                self.cleaned_data["username"] = account.get_username()
        return super().clean()


class StudentRegistrationForm(forms.Form):
    STUDENT_STATUS_CHOICES = (
        (StudentProfile.Status.CURRENT, "Current final-year student"),
        (StudentProfile.Status.FYP_COMPLETED, "Past final-year student (FYP completed)"),
    )

    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    email = forms.EmailField(label="Baze email address")
    student_number = forms.CharField(max_length=30, label="Student ID")
    programme = forms.ModelChoiceField(
        queryset=Programme.objects.none(),
        empty_label="Select your programme",
        label="Programme",
    )
    student_status = forms.ChoiceField(
        choices=STUDENT_STATUS_CHOICES,
        label="Student status",
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["programme"].queryset = Programme.objects.select_related("department")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not email.endswith(BAZE_EMAIL_DOMAIN):
            raise ValidationError(f"Use your Baze email address ending in {BAZE_EMAIL_DOMAIN}.")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account already exists with this email address.")
        if User.objects.filter(username__iexact=email).exists():
            raise ValidationError("An account already exists with this email address.")
        return email

    def clean_student_number(self):
        student_number = self.cleaned_data["student_number"].strip()
        if StudentProfile.objects.filter(student_number__iexact=student_number).exists():
            raise ValidationError("An account already exists with this student ID.")
        return student_number

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        elif password1:
            user = User(
                username=cleaned_data.get("email", ""),
                email=cleaned_data.get("email", ""),
                first_name=cleaned_data.get("first_name", ""),
                last_name=cleaned_data.get("last_name", ""),
            )
            try:
                validate_password(password1, user=user)
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned_data

    @transaction.atomic
    def save(self):
        programme = self.cleaned_data["programme"]
        user = User.objects.create_user(
            username=self.cleaned_data["email"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            role=Role.STUDENT,
            department=programme.department,
            is_active=False,
        )
        StudentProfile.objects.create(
            user=user,
            student_number=self.cleaned_data["student_number"],
            programme=programme,
            student_status=self.cleaned_data["student_status"],
            registration_status=StudentProfile.RegistrationStatus.PENDING,
        )
        return user


def _check_new_baze_email(value):
    email = value.strip().lower()
    if not email.endswith(BAZE_EMAIL_DOMAIN):
        raise ValidationError(f"Use a Baze email address ending in {BAZE_EMAIL_DOMAIN}.")
    if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
        raise ValidationError("An account already exists with this email address.")
    return email


class StaffAccountForm(forms.Form):
    """Admin-only: create a supervisor, coordinator, HOD or administrator account.

    Staff roles are never chosen by the person themselves (student sign-up cannot set a role), so
    nobody can grant themselves staff access. The password is generated here, shown to the admin
    once, and must be changed at first sign-in.
    """

    ROLE_CHOICES = [(role.value, role.label) for role in STAFF_ROLES]
    TEMPORARY_PASSWORD_BYTES = 12  # 16 URL-safe characters

    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    email = forms.EmailField(label="Baze email address", help_text="Also their sign-in username.")
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="Role")
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(), required=False, empty_label="Select a department",
        label="Department", help_text="Required for every role except Administrator.",
    )
    title = forms.CharField(max_length=30, required=False, label="Title", help_text="For example Dr., Prof., Mrs.")
    can_assign_supervisors = forms.BooleanField(
        required=False, label="Can assign supervisors in their department",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.select_related("faculty")

    def clean_email(self):
        return _check_new_baze_email(self.cleaned_data["email"])

    def clean(self):
        cleaned = super().clean()
        role, department = cleaned.get("role"), cleaned.get("department")
        if role and role != Role.ADMIN and department is None:
            self.add_error("department", "Choose the department this staff member belongs to.")
        if role == Role.ADMIN:
            cleaned["department"] = None
            cleaned["can_assign_supervisors"] = False
        return cleaned

    @transaction.atomic
    def save(self):
        """Create the account. Returns (user, temporary_password); the password is not stored anywhere else."""
        password = secrets.token_urlsafe(self.TEMPORARY_PASSWORD_BYTES)
        data = self.cleaned_data
        user = User.objects.create_user(
            username=data["email"], email=data["email"], password=password,
            first_name=data["first_name"], last_name=data["last_name"],
            role=data["role"], department=data["department"],
            can_assign_supervisors=data["can_assign_supervisors"], must_change_password=True,
        )
        if data["role"] != Role.ADMIN:
            SupervisorProfile.objects.create(user=user, title=data["title"])
        return user, password
