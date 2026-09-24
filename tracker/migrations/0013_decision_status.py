from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0012_decision"),
    ]

    operations = [
        migrations.AddField(
            model_name="decision",
            name="status",
            field=models.CharField(
                choices=[("ongoing", "Ongoing"), ("completed", "Completed"), ("abandoned", "Abandoned")],
                default="ongoing",
                max_length=20,
            ),
        ),
    ]
