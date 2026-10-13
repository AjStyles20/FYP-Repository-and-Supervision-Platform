"""Admin forms for the Faculty > Department > Programme tree."""

from django import forms

from .models import Department, Faculty, Programme, Semester


class FacultyForm(forms.ModelForm):
    class Meta:
        model = Faculty
        fields = ("name", "code")


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ("faculty", "name", "code")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["faculty"].empty_label = "Select a faculty"


class ProgrammeForm(forms.ModelForm):
    class Meta:
        model = Programme
        fields = ("department", "name", "degree_type", "level", "duration_years")
        labels = {"degree_type": "Award", "duration_years": "Duration (years)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.select_related("faculty")
        self.fields["department"].empty_label = "Select a department"


FORMS = {"faculty": FacultyForm, "department": DepartmentForm, "programme": ProgrammeForm}
MODELS = {"faculty": Faculty, "department": Department, "programme": Programme}


class SemesterForm(forms.ModelForm):
    """A semester label entered by hand (D-38); the dates are optional notes."""

    class Meta:
        model = Semester
        fields = ("code", "starts_on", "ends_on")
        labels = {"code": "Semester", "starts_on": "Starts on", "ends_on": "Ends on"}
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "26A", "autocapitalize": "characters", "maxlength": 3}),
            "starts_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "ends_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()
