from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import Programme

from .models import Role, StudentProfile, User

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
