import django.utils.timezone
from django.db import migrations, models
from django_mongodb_backend.fields import ObjectIdAutoField


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0011_meeting"),
    ]

    operations = [
        migrations.CreateModel(
            name="Decision",
            fields=[
                ("id", ObjectIdAutoField(primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("motivation", models.TextField(blank=True)),
                ("rollback_reasons", models.TextField(blank=True)),
                ("start_date", models.DateField(default=django.utils.timezone.localdate)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="decisions_created", to="tracker.member")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="children", to="tracker.decision")),
            ],
            options={"ordering": ["start_date", "title"]},
        ),
    ]
