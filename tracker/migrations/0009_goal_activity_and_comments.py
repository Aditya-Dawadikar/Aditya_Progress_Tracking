from django.db import migrations, models
from django_mongodb_backend.fields import ObjectIdAutoField


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0008_scope_categories_to_boards"),
    ]

    operations = [
        migrations.CreateModel(
            name="GoalActivity",
            fields=[
                ("id", ObjectIdAutoField(primary_key=True, serialize=False)),
                ("action", models.CharField(max_length=50)),
                ("detail", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, related_name="goal_activity", to="tracker.member")),
                ("goal", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="activity", to="tracker.goal")),
                ("task", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name="activity", to="tracker.todotask")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="GoalComment",
            fields=[
                ("id", ObjectIdAutoField(primary_key=True, serialize=False)),
                ("text", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="goal_comments", to="tracker.member")),
                ("goal", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="comments", to="tracker.goal")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="TodoTaskComment",
            fields=[
                ("id", ObjectIdAutoField(primary_key=True, serialize=False)),
                ("text", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="task_comments", to="tracker.member")),
                ("task", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="comments", to="tracker.todotask")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]