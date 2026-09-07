from django.db import migrations, models
from django_mongodb_backend.fields import ObjectIdAutoField


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0010_event_and_event_comment"),
    ]

    operations = [
        migrations.CreateModel(
            name="Meeting",
            fields=[
                ("id", ObjectIdAutoField(primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("notes", models.TextField(blank=True)),
                ("when", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="meetings_created", to="tracker.member")),
                ("participants", models.ManyToManyField(blank=True, related_name="meetings", to="tracker.member")),
            ],
            options={"ordering": ["when", "title"]},
        ),
    ]
