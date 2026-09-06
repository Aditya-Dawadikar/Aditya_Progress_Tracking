from django.db import migrations, models


def scope_categories_to_boards(apps, schema_editor):
    Category = apps.get_model("tracker", "Category")
    Goal = apps.get_model("tracker", "Goal")

    for category in Category.objects.all():
        goals = list(Goal.objects.filter(category=category).select_related("board"))
        if not goals:
            category.delete()
            continue
        category.board = goals[0].board
        category.save(update_fields=["board"])
        for goal in goals[1:]:
            if goal.board_id == category.board_id:
                continue
            scoped_category, _ = Category.objects.get_or_create(
                board=goal.board,
                name=category.name,
                defaults={"color": category.color, "created_by": category.created_by},
            )
            goal.category = scoped_category
            goal.save(update_fields=["category"])


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0007_add_assignees"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="board",
            field=models.ForeignKey(null=True, on_delete=models.deletion.CASCADE, related_name="categories", to="tracker.goalboard"),
        ),
        migrations.RunPython(scope_categories_to_boards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="category",
            name="board",
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="categories", to="tracker.goalboard"),
        ),
        migrations.AlterField(
            model_name="category",
            name="name",
            field=models.CharField(max_length=50),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(fields=("board", "name"), name="unique_category_name_per_board"),
        ),
    ]