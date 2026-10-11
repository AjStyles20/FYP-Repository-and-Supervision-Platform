"""Contact details move from StudentProfile to User, so staff can have them too, with a phone number.

An existing student contact email is copied to personal_email. If the student had consented, it
stays visible to signed-in Baze users (as before); otherwise it is visible only to its owner.
"""

import apps.accounts.models
from django.db import migrations, models


def copy_student_contacts(apps, schema_editor):
    StudentProfile = apps.get_model("accounts", "StudentProfile")
    User = apps.get_model("accounts", "User")
    for profile in StudentProfile.objects.exclude(contact_email=""):
        User.objects.filter(pk=profile.user_id).update(
            personal_email=profile.contact_email,
            personal_email_visibility="signed_in" if profile.contact_consent else "hidden",
        )


def copy_back(apps, schema_editor):
    StudentProfile = apps.get_model("accounts", "StudentProfile")
    for profile in StudentProfile.objects.select_related("user").exclude(user__personal_email=""):
        profile.contact_email = profile.user.personal_email
        profile.contact_consent = profile.user.personal_email_visibility == "signed_in"
        profile.save(update_fields=["contact_email", "contact_consent"])


VISIBILITY = [("hidden", "Only me"), ("staff", "Staff only"), ("signed_in", "All signed-in Baze users")]


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_user_must_change_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="personal_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="user",
            name="personal_email_visibility",
            field=models.CharField(choices=VISIBILITY, default="hidden", max_length=10),
        ),
        migrations.AddField(
            model_name="user",
            name="phone",
            field=models.CharField(blank=True, max_length=20, validators=[apps.accounts.models.phone_validator]),
        ),
        migrations.AddField(
            model_name="user",
            name="phone_visibility",
            field=models.CharField(choices=VISIBILITY, default="hidden", max_length=10),
        ),
        migrations.RunPython(copy_student_contacts, copy_back),
        migrations.RemoveField(model_name="studentprofile", name="contact_email"),
        migrations.RemoveField(model_name="studentprofile", name="contact_consent"),
    ]
