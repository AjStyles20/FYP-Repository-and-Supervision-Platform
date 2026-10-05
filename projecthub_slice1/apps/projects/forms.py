from django import forms

from apps.accounts.models import User


class SupervisorAssignmentForm(forms.Form):
    supervisor = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Assign supervisor",
        empty_label="Choose a supervisor",
    )
    reason = forms.CharField(
        required=False,
        max_length=1000,
        label="Reason for assignment or change",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, supervisor_queryset, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supervisor"].queryset = supervisor_queryset
