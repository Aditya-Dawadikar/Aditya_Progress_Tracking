from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0006_todotask_due_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="goal",
            name="assignees",
            field=models.ManyToManyField(blank=True, related_name="assigned_goals", to="tracker.member"),
        ),
        migrations.AddField(
            model_name="todotask",
            name="assignees",
            field=models.ManyToManyField(blank=True, related_name="assigned_tasks", to="tracker.member"),
        ),
    ]