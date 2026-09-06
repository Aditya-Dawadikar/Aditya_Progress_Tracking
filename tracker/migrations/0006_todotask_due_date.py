from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0005_replace_subgoals_with_tasks"),
    ]

    operations = [
        migrations.AddField(
            model_name="todotask",
            name="due_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]