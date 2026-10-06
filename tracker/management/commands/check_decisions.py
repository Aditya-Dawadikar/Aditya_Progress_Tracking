"""Read-only report on whether stored decision documents fit the current schema.

Run it before deploying a schema change (it reads raw documents, so it works
whether or not the latest migration has been applied) and again afterwards:

    python manage.py check_decisions

Exits non-zero if anything would break the decisions UI.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from tracker.models import Decision

STATUSES = {value for value, _ in Decision.STATUS_CHOICES}
REQUIRED = ["title", "start_date", "created_by_id", "created_at", "updated_at"]


class Command(BaseCommand):
    help = "Check stored decisions against the multi-parent schema (read-only)."

    def handle(self, *args, **options):
        db = connection.database
        decisions = list(db["tracker_decision"].find({}, {"description": 0, "motivation": 0, "rollback_reasons": 0}))
        ids = {d["_id"] for d in decisions}
        members = set(db["tracker_member"].distinct("_id"))
        links = list(db["tracker_decision_parents"].find()) if "tracker_decision_parents" in db.list_collection_names() else []
        applied = MigrationRecorder(connection).applied_migrations()
        migrated = ("tracker", "0014_decision_multiple_parents") in applied

        problems, notes = [], []
        self.stdout.write(f"{len(decisions)} decisions, {len(links)} parent links, 0014 applied: {migrated}")

        legacy = [d for d in decisions if d.get("parent_id") is not None]
        dangling_legacy = {d["_id"] for d in legacy if d["parent_id"] not in ids or d["parent_id"] == d["_id"]}
        if migrated and any("parent_id" in d for d in decisions):
            problems.append(f"{sum('parent_id' in d for d in decisions)} documents still carry the old parent_id field")
        elif not migrated:
            notes.append(
                f"0014 will turn {len(legacy) - len(dangling_legacy)} parent_id values into parent links"
                + (f" and drop {len(dangling_legacy)} that point at missing decisions" if dangling_legacy else "")
            )

        bad_links = [l for l in links if l.get("from_decision_id") not in ids or l.get("to_decision_id") not in ids]
        if bad_links:
            problems.append(f"{len(bad_links)} parent links point at missing decisions")
        self_links = [l for l in links if l.get("from_decision_id") == l.get("to_decision_id")]
        if self_links:
            problems.append(f"{len(self_links)} decisions list themselves as a parent")

        missing_status = [d for d in decisions if d.get("status") is None]
        if missing_status:
            (notes if not migrated else problems).append(
                f"{len(missing_status)} decisions have no status" + (" (0014 sets them to ongoing)" if not migrated else "")
            )
        bad_status = [d for d in decisions if d.get("status") is not None and d["status"] not in STATUSES]
        if bad_status:
            problems.append(f"{len(bad_status)} decisions have an unknown status: {sorted({d['status'] for d in bad_status})}")
        for field in REQUIRED:
            missing = [d for d in decisions if d.get(field) is None]
            if missing:
                problems.append(f"{len(missing)} decisions are missing {field}")
        orphaned = [d for d in decisions if d.get("created_by_id") is not None and d["created_by_id"] not in members]
        if orphaned:
            problems.append(f"{len(orphaned)} decisions reference a deleted member")

        edges = [(l["from_decision_id"], l["to_decision_id"]) for l in links] if migrated else [
            (d["_id"], d["parent_id"]) for d in legacy if d["_id"] not in dangling_legacy
        ]
        if self._has_cycle(edges):
            problems.append("parent links contain a cycle")

        for note in notes:
            self.stdout.write(f"  note: {note}")
        for problem in problems:
            self.stdout.write(self.style.ERROR(f"  problem: {problem}"))
        if problems:
            raise CommandError("Decision documents need attention before they fit the current schema.")
        self.stdout.write(self.style.SUCCESS("Decision documents are compatible."))

    @staticmethod
    def _has_cycle(edges):
        parents = {}
        for child, parent in edges:
            parents.setdefault(child, []).append(parent)
        state = {}  # 1 = on the current path, 2 = done

        for start in parents:
            if state.get(start):
                continue
            state[start] = 1
            stack = [(start, iter(parents[start]))]
            while stack:
                node, it = stack[-1]
                nxt = next(it, None)
                if nxt is None:
                    state[node] = 2
                    stack.pop()
                elif state.get(nxt) == 1:
                    return True
                elif not state.get(nxt):
                    state[nxt] = 1
                    stack.append((nxt, iter(parents.get(nxt, []))))
        return False
