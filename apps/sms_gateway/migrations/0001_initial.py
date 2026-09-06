from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RegistrationSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone_number", models.CharField(max_length=16, unique=True)),
                (
                    "current_step",
                    models.CharField(
                        choices=[
                            ("awaiting_name", "Awaiting name"),
                            ("awaiting_business_name", "Awaiting business name"),
                            ("awaiting_business_type", "Awaiting business type"),
                            ("awaiting_tracking_frequency", "Awaiting tracking frequency"),
                            ("complete", "Complete"),
                        ],
                        default="awaiting_name",
                        max_length=32,
                    ),
                ),
                ("collected_full_name", models.CharField(blank=True, max_length=255)),
                ("collected_business_name", models.CharField(blank=True, max_length=255)),
                ("collected_business_type", models.CharField(blank=True, max_length=32)),
                ("collected_tracking_frequency", models.CharField(blank=True, max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
