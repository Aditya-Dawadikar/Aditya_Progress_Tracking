from django.db import migrations, models
from django_mongodb_backend.fields import ObjectIdAutoField


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0009_goal_activity_and_comments"),
    ]

    operations = [
        migrations.CreateModel(
            name="Event",
            fields=[
                ("id", ObjectIdAutoField(primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("date", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="events_created", to="tracker.member")),
                ("participants", models.ManyToManyField(blank=True, related_name="events", to="tracker.member")),
            ],
            options={"ordering": ["date", "title"]},
        ),
        migrations.CreateModel(
            name="EventComment",
            fields=[
                ("id", ObjectIdAutoField(primary_key=True, serialize=False)),
                ("text", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="event_comments", to="tracker.member")),
                ("event", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="comments", to="tracker.event")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]