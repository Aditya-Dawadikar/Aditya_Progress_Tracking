from django.db import migrations

DEFAULT_CATEGORIES = [
    ("Financial", "#4F7A62"),
    ("Health", "#E6A65D"),
    ("Career", "#7B6DCC"),
    ("Personal", "#5C8FC7"),
]
PALETTE = ["#4F7A62", "#E6A65D", "#7B6DCC", "#5C8FC7", "#C1584A", "#4FA39A", "#C77DAE", "#8A8578"]


def seed_and_migrate(apps, schema_editor):
    Category = apps.get_model("tracker", "Category")
    Goal = apps.get_model("tracker", "Goal")

    by_name = {}
    for name, color in DEFAULT_CATEGORIES:
        category, _ = Category.objects.get_or_create(name=name, defaults={"color": color})
        by_name[name.lower()] = category

    existing_values = (
        Goal.objects.exclude(category="").values_list("category", flat=True).distinct()
    )
    palette_index = len(DEFAULT_CATEGORIES)
    for raw_name in existing_values:
        key = raw_name.strip()
        if not key:
            continue
        if key.lower() in by_name:
            category = by_name[key.lower()]
        else:
            category, created = Category.objects.get_or_create(
                name=key, defaults={"color": PALETTE[palette_index % len(PALETTE)]}
            )
            if created:
                palette_index += 1
            by_name[key.lower()] = category
        Goal.objects.filter(category=raw_name).update(category_ref=category)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0002_category_and_optional_dates'),
    ]

    operations = [
        migrations.RunPython(seed_and_migrate, noop_reverse),
    ]
