from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0003_seed_and_migrate_categories'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='goal',
            name='category',
        ),
        migrations.RenameField(
            model_name='goal',
            old_name='category_ref',
            new_name='category',
        ),
    ]
