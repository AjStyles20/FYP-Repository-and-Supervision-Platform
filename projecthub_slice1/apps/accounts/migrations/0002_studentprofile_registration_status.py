from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="registration_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending approval"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                ],
                default="approved",
                max_length=10,
            ),
        ),
    ]
