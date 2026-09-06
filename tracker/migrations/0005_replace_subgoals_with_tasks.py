from django.db import migrations, models
from django_mongodb_backend.fields import ObjectIdAutoField


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0004_finalize_category_field"),
    ]

    operations = [
        migrations.CreateModel(
            name="TodoTask",
            fields=[
                ("id", ObjectIdAutoField(primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("completed", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("goal", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="tasks", to="tracker.goal")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.RemoveField(
            model_name="goal",
            name="parent",
        ),
    ]