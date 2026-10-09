"""Admin forms for the Faculty > Department > Programme tree."""

from django import forms

from .models import Department, Faculty, Programme


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
