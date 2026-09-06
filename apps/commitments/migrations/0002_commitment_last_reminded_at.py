from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("commitments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="commitment",
            name="last_reminded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
