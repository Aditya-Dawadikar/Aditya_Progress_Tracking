"""Replace Decision.parent (one optional parent) with Decision.parents (many).

Existing documents are carried over: every stored ``parent_id`` that still
points at an existing decision becomes a link in the new
``tracker_decision_parents`` collection, then the old ``parent_id`` field is
unset on every decision document. Dangling or self-referencing ids are dropped
since the UI could never have shown them anyway. The copy step skips links
that already exist, so re-running after a partial failure is safe.

Reversing keeps each decision's earliest parent (by start date) as its single
parent.
"""

from django.db import migrations, models


def copy_parent_to_parents(apps, schema_editor):
    Decision = apps.get_model("tracker", "Decision")
    Link = Decision.parents.through
    existing = set(Decision.objects.values_list("pk", flat=True))
    already = set(Link.objects.values_list("from_decision_id", "to_decision_id"))
    links = [
        Link(from_decision_id=pk, to_decision_id=parent_id)
        for pk, parent_id in Decision.objects.values_list("pk", "parent_id")
        if parent_id is not None and parent_id != pk and parent_id in existing and (pk, parent_id) not in already
    ]
    if links:
        Link.objects.bulk_create(links)
    # Decisions recorded before 0013 got a status from its default; make sure
    # nothing slipped through without one, since the UI renders it everywhere.
    Decision.objects.filter(status=None).update(status="ongoing")


def keep_earliest_parent(apps, schema_editor):
    Decision = apps.get_model("tracker", "Decision")
    for decision in Decision.objects.all():
        first = decision.parents.order_by("start_date", "pk").first()
        if first is not None:
            Decision.objects.filter(pk=decision.pk).update(parent=first)


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0013_decision_status"),
    ]

    operations = [
        # The old FK's reverse accessor is "children" too; free that name before
        # adding the new field so both can coexist while data is copied.
        migrations.AlterField(
            model_name="decision",
            name="parent",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="+", to="tracker.decision"
            ),
        ),
        migrations.AddField(
            model_name="decision",
            name="parents",
            field=models.ManyToManyField(blank=True, related_name="children", to="tracker.decision"),
        ),
        migrations.RunPython(copy_parent_to_parents, keep_earliest_parent),
        migrations.RemoveField(model_name="decision", name="parent"),
    ]
