import csv
import datetime
import io
import json

from bson import ObjectId
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .auth import issue_token
from .forms import DecisionForm
from .models import Category, Decision, Event, EventComment, Goal, GoalActivity, GoalBoard, GoalComment, Member, TodoTask, TodoTaskComment
from .services import goal_io
from .services.scoring import member_leaderboard


def days(n):
    return timezone.localdate() + datetime.timedelta(days=n)


class GoalModelTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Alex")
        self.board = GoalBoard.objects.create(name="Test Board", created_by=self.member)

    def make_goal(self, **kwargs):
        defaults = dict(
            board=self.board, owner=self.member, title="Goal",
            start_date=days(-10), end_date=days(10),
        )
        defaults.update(kwargs)
        return Goal.objects.create(**defaults)

    def test_effective_progress_is_own_percent_for_leaf(self):
        goal = self.make_goal(progress_percent=40)
        self.assertEqual(goal.effective_progress, 40)

    def test_effective_progress_is_derived_from_tasks(self):
        goal = self.make_goal()
        TodoTask.objects.create(goal=goal, title="Done", completed=True)
        TodoTask.objects.create(goal=goal, title="Remaining", completed=False)
        self.assertEqual(goal.effective_progress, 50)

    def test_task_deadline_labels_overdue_and_remaining_days(self):
        goal = self.make_goal()
        overdue = TodoTask.objects.create(goal=goal, title="Late", due_date=days(-2))
        upcoming = TodoTask.objects.create(goal=goal, title="Soon", due_date=days(3))
        self.assertTrue(overdue.is_overdue)
        self.assertEqual(overdue.deadline_label, "Overdue by 2 days")
        self.assertFalse(upcoming.is_overdue)
        self.assertEqual(upcoming.deadline_label, "3 days left")

    def test_goal_activity_and_comments_are_attributed_to_members(self):
        goal = self.make_goal()
        task = TodoTask.objects.create(goal=goal, title="Task")
        event = GoalActivity.objects.create(goal=goal, task=task, actor=self.member, action="task_created")
        goal_comment = GoalComment.objects.create(goal=goal, author=self.member, text="Goal note")
        task_comment = TodoTaskComment.objects.create(task=task, author=self.member, text="Task note")
        self.assertEqual(goal.activity.get(), event)
        self.assertEqual(goal.comments.get(), goal_comment)
        self.assertEqual(task.comments.get(), task_comment)

    def test_completing_a_goal_sets_full_progress(self):
        goal = self.make_goal(progress_percent=10)
        goal.status = Goal.STATUS_COMPLETED
        goal.save()
        self.assertEqual(goal.progress_percent, 100)
        self.assertIsNotNone(goal.completed_at)

    def test_pace_score_ahead_of_schedule(self):
        # Halfway through the window but fully done -> well above 50.
        goal = self.make_goal(start_date=days(-10), end_date=days(10), progress_percent=100)
        self.assertGreater(goal.pace_score, 50)

    def test_pace_score_behind_schedule(self):
        goal = self.make_goal(start_date=days(-10), end_date=days(10), progress_percent=0)
        self.assertLess(goal.pace_score, 50)

    def test_pace_score_is_none_without_a_deadline(self):
        goal = self.make_goal(start_date=None, end_date=None, progress_percent=50)
        self.assertIsNone(goal.pace_score)
        self.assertIsNone(goal.time_fraction_percent)
        self.assertFalse(goal.is_overdue)

    def test_dateless_goal_saves_and_validates_cleanly(self):
        goal = self.make_goal(start_date=None, end_date=None)
        goal.full_clean(exclude=["board"])


class ScoringServiceTests(TestCase):
    def test_leaderboard_ranks_ahead_member_above_behind_member(self):
        board = GoalBoard.objects.create(name="Board")
        ahead = Member.objects.create(name="Ahead")
        behind = Member.objects.create(name="Behind")
        Goal.objects.create(
            board=board, owner=ahead, title="Ahead goal",
            start_date=days(-10), end_date=days(10), progress_percent=100,
        )
        Goal.objects.create(
            board=board, owner=behind, title="Behind goal",
            start_date=days(-10), end_date=days(10), progress_percent=0,
        )
        ranked = member_leaderboard()
        self.assertEqual(ranked[0].name, "Ahead")
        self.assertEqual(ranked[-1].name, "Behind")

    def test_goals_without_deadlines_are_excluded_from_scoring(self):
        board = GoalBoard.objects.create(name="Board")
        member = Member.objects.create(name="NoDeadline")
        Goal.objects.create(
            board=board, owner=member, title="Someday",
            start_date=None, end_date=None, progress_percent=10,
        )
        ranked = member_leaderboard()
        row = next(m for m in ranked if m.name == "NoDeadline")
        self.assertIsNone(row.score)


class EventModelTests(TestCase):
    def test_event_tracks_participants_and_comment_author(self):
        creator = Member.objects.create(name="Alex")
        participant = Member.objects.create(name="Sam")
        event = Event.objects.create(title="Planning day", date=days(3), created_by=creator)
        event.participants.add(creator, participant)
        comment = EventComment.objects.create(event=event, author=participant, text="I'll be there.")
        self.assertFalse(event.is_past)
        self.assertEqual(list(event.participants.all()), [creator, participant])
        self.assertEqual(event.comments.get(), comment)


class DecisionTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Alex")
        self.root = Decision.objects.create(title="Use MongoDB", created_by=self.member)
        self.child = Decision.objects.create(title="Add indexes", created_by=self.member)
        self.child.parents.add(self.root)
        self.client.cookies[settings.JWT_COOKIE_NAME] = issue_token()
        session = self.client.session
        session["member_id"] = str(self.member.pk)
        session.save()

    def test_chain_links_parents_and_children(self):
        grandchild = Decision.objects.create(title="Drop index", created_by=self.member)
        grandchild.parents.add(self.child)
        self.assertEqual(grandchild.ancestor_ids(), {self.root.pk, self.child.pk})
        self.assertEqual(self.root.descendant_ids(), {self.child.pk, grandchild.pk})

    def test_parent_can_be_found_by_title_or_id(self):
        base = {"title": "Next", "status": "ongoing", "start_date": days(0)}
        for ref in ["use mongodb", str(self.root.pk), f"Use MongoDB [{self.root.pk}]"]:
            form = DecisionForm(data={**base, "parent_refs": ref})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["parent_refs"], [self.root])

    def test_decision_can_have_several_parents(self):
        other = Decision.objects.create(title="Self-host", created_by=self.member)
        response = self.client.post(reverse("tracker:decision_create"), {
            "title": "Run Mongo on Railway", "status": "ongoing", "start_date": days(0),
            "parent_refs": [f"Add indexes [{self.child.pk}]", "self-host", "", str(other.pk)],
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        decision = Decision.objects.get(title="Run Mongo on Railway")
        self.assertEqual(set(decision.parents.all()), {self.child, other})
        self.assertEqual(decision.ancestor_ids(), {self.root.pk, self.child.pk, other.pk})

        form = DecisionForm(instance=decision)
        self.assertEqual(form.initial["parent_refs"], [f"Add indexes [{self.child.pk}]", f"Self-host [{other.pk}]"])
        response = self.client.post(reverse("tracker:decision_edit", args=[decision.pk]), {
            "title": decision.title, "status": "ongoing", "start_date": days(0), "parent_refs": [str(other.pk)],
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(decision.parents.all()), [other])

    def test_every_bad_parent_ref_is_reported(self):
        form = DecisionForm(data={"title": "X", "status": "ongoing", "start_date": days(0), "parent_refs": ["nope", "use mongodb", "zilch"]})
        self.assertFalse(form.is_valid())
        self.assertEqual(len(form.errors["parent_refs"]), 2)

    def test_parent_cannot_create_a_cycle(self):
        form = DecisionForm(data={"title": "Use MongoDB", "status": "ongoing", "start_date": days(0), "parent_refs": str(self.child.pk)}, instance=self.root)
        self.assertFalse(form.is_valid())
        self.assertIn("parent_refs", form.errors)

    def test_end_date_must_follow_start_date(self):
        form = DecisionForm(data={"title": "X", "status": "ongoing", "start_date": days(0), "end_date": days(-1)})
        self.assertFalse(form.is_valid())
        self.assertIn("end_date", form.errors)

    def test_deleting_relinks_children_to_grandparents(self):
        other = Decision.objects.create(title="Self-host", created_by=self.member)
        self.child.parents.add(other)
        grandchild = Decision.objects.create(title="Drop index", created_by=self.member)
        grandchild.parents.add(self.child)
        response = self.client.post(reverse("tracker:decision_delete", args=[self.child.pk]), {"name": "Add indexes"}, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(grandchild.parents.all()), {self.root, other})
        self.assertFalse(Decision.parents.through.objects.filter(to_decision_id=self.child.pk).exists())

    def test_filter_by_status(self):
        self.child.status = Decision.STATUS_ABANDONED
        self.child.save()
        self.assertEqual(self.root.status, Decision.STATUS_ONGOING)
        response = self.client.get(reverse("tracker:decisions_list") + "?status=abandoned", secure=True)
        self.assertEqual(list(response.context["decisions"]), [self.child])
        response = self.client.get(reverse("tracker:decisions_list") + "?status=ongoing", secure=True)
        self.assertEqual(list(response.context["decisions"]), [self.root])

    def _export_rows(self, query=""):
        response = self.client.get(reverse("tracker:decisions_export_csv") + query, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment;", response["Content-Disposition"])
        return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))

    def test_export_csv_includes_every_decision(self):
        rows = self._export_rows()
        self.assertEqual([r["title"] for r in rows], ["Use MongoDB", "Add indexes"])
        self.assertEqual(rows[1]["parent_ids"], str(self.root.pk))
        self.assertEqual(rows[1]["parent_titles"], "Use MongoDB")
        self.assertEqual(rows[0]["created_by"], "Alex")

    def test_export_csv_honours_list_filters(self):
        self.child.status = Decision.STATUS_ABANDONED
        self.child.save()
        rows = self._export_rows("?status=abandoned")
        self.assertEqual([r["id"] for r in rows], [str(self.child.pk)])
        self.assertEqual(rows[0]["status"], "Abandoned")
        self.assertEqual([r["title"] for r in self._export_rows("?q=mongo")], ["Use MongoDB"])

    def test_export_csv_neutralises_formulas(self):
        Decision.objects.create(title="=HYPERLINK(\"http://x\")", created_by=self.member)
        titles = [r["title"] for r in self._export_rows("?q=HYPERLINK")]
        self.assertEqual(titles, ["'=HYPERLINK(\"http://x\")"])

    def test_list_offers_filtered_export_only_when_filtering(self):
        response = self.client.get(reverse("tracker:decisions_list"), secure=True)
        self.assertNotContains(response, "filtered (CSV)")
        response = self.client.get(reverse("tracker:decisions_list") + "?status=ongoing", secure=True)
        self.assertContains(response, reverse("tracker:decisions_export_csv") + "?status=ongoing")

    def test_explorer_and_list_show_every_parent(self):
        other = Decision.objects.create(title="Self-host", start_date=days(1), created_by=self.member)
        self.child.parents.add(other)
        response = self.client.get(reverse("tracker:decisions_list"), secure=True)
        data = {d["id"]: d for d in response.context["explorer"]}
        self.assertEqual(data[str(self.root.pk)]["parents"], [])
        self.assertEqual(set(data[str(self.child.pk)]["parents"]), {str(self.root.pk), str(other.pk)})
        self.assertContains(response, "Follows “Use MongoDB”, “Self-host”")
        response = self.client.get(reverse("tracker:decision_detail", args=[self.child.pk]), secure=True)
        self.assertContains(response, other.get_absolute_url())

    def test_pages_render(self):
        for url in [
            reverse("tracker:decisions_graph"),
            reverse("tracker:decisions_list"),
            reverse("tracker:decisions_list") + f"?q={self.root.pk}",
            reverse("tracker:decision_detail", args=[self.child.pk]),
            reverse("tracker:decision_create"),
            reverse("tracker:decision_edit", args=[self.root.pk]),
        ]:
            response = self.client.get(url, secure=True)
            self.assertEqual(response.status_code, 200, url)


class DecisionParentsMigrationTests(TransactionTestCase):
    """0014 must carry documents written under the single-parent schema over."""

    before = [("tracker", "0013_decision_status")]
    after = [("tracker", "0014_decision_multiple_parents")]

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_single_parent_documents_become_parent_links(self):
        apps = self.migrate(self.before)
        OldMember = apps.get_model("tracker", "Member")
        OldDecision = apps.get_model("tracker", "Decision")
        member = OldMember.objects.create(name="Alex")
        root = OldDecision.objects.create(title="Root", created_by=member)
        child = OldDecision.objects.create(title="Child", created_by=member, parent=root)
        orphan = OldDecision.objects.create(title="Orphan", created_by=member)
        # Shapes older or hand-edited data can have: a parent id pointing at a
        # deleted decision, and a document saved without a status field.
        decisions = connection.database["tracker_decision"]
        decisions.update_one({"_id": orphan.pk}, {"$set": {"parent_id": ObjectId()}})
        now = timezone.now()
        legacy = decisions.insert_one({
            "title": "Legacy", "description": "", "motivation": "", "rollback_reasons": "",
            "start_date": datetime.datetime.combine(days(0), datetime.time()), "end_date": None,
            "parent_id": child.pk, "created_by_id": member.pk, "created_at": now, "updated_at": now,
        }).inserted_id

        apps = self.migrate(self.after)
        NewDecision = apps.get_model("tracker", "Decision")
        self.assertEqual(list(NewDecision.objects.get(pk=child.pk).parents.values_list("pk", flat=True)), [root.pk])
        self.assertEqual(list(NewDecision.objects.get(pk=legacy).parents.values_list("pk", flat=True)), [child.pk])
        self.assertFalse(NewDecision.objects.get(pk=orphan.pk).parents.exists())
        self.assertFalse(NewDecision.objects.get(pk=root.pk).parents.exists())
        self.assertEqual(NewDecision.objects.get(pk=legacy).status, "ongoing")
        self.assertEqual(decisions.count_documents({"parent_id": {"$exists": True}}), 0)

        # Rolling back keeps a single parent per decision.
        apps = self.migrate(self.before)
        OldDecision = apps.get_model("tracker", "Decision")
        self.assertEqual(OldDecision.objects.get(pk=child.pk).parent_id, root.pk)
        self.assertEqual(OldDecision.objects.get(pk=legacy).parent_id, child.pk)
        self.assertIsNone(OldDecision.objects.get(pk=orphan.pk).parent_id)


class ViewSmokeTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Alex")
        self.board = GoalBoard.objects.create(name="Board", created_by=self.member)
        self.goal = Goal.objects.create(
            board=self.board, owner=self.member, title="Goal",
            start_date=days(-5), end_date=days(5),
        )

    def test_public_pages_render_without_a_member(self):
        for url in [
            reverse("tracker:boards_list"),
            reverse("tracker:board_detail", args=[self.board.pk]),
            reverse("tracker:goal_detail", args=[self.goal.pk]),
            reverse("tracker:leaderboard"),
            reverse("tracker:member_profile", args=[self.member.slug]),
        ]:
            response = self.client.get(url, secure=True)
            self.assertEqual(response.status_code, 200, url)

    def test_goal_create_requires_a_member(self):
        url = reverse("tracker:goal_create") + f"?board={self.board.pk}"
        response = self.client.get(url, secure=True)
        self.assertRedirects(
            response, f"{reverse('tracker:whoami')}?next={url}", fetch_redirect_response=False
        )

    def test_whoami_sets_session_member(self):
        response = self.client.post(reverse("tracker:whoami"), {"name": "New Person"}, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Member.objects.filter(name="New Person").exists())
        self.assertEqual(self.client.session["member_id"], str(Member.objects.get(name="New Person").pk))

    def test_reorder_updates_status_and_order(self):
        second = Goal.objects.create(
            board=self.board, owner=self.member, title="Goal 2",
            start_date=days(-5), end_date=days(5),
        )
        self.client.post(reverse("tracker:whoami"), {"action": "switch", "member_id": self.member.pk}, secure=True)
        response = self.client.post(
            reverse("tracker:goal_reorder"),
            data=json.dumps({
                "scope": "board",
                "scope_id": str(self.board.pk),
                "columns": {"in_progress": [str(second.pk), str(self.goal.pk)]},
            }),
            content_type="application/json",
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.goal.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.goal.status, Goal.STATUS_IN_PROGRESS)
        self.assertEqual(second.order, 0)
        self.assertEqual(self.goal.order, 1)

    def test_cannot_add_task_to_another_members_goal(self):
        other = Member.objects.create(name="Other")
        self.client.post(reverse("tracker:whoami"), {"action": "switch", "member_id": other.pk}, secure=True)
        response = self.client.post(reverse("tracker:task_create", args=[self.goal.pk]), {"title": "Sneaky task"}, secure=True)
        self.assertRedirects(response, self.goal.get_absolute_url(), fetch_redirect_response=False)
        self.assertFalse(self.goal.tasks.exists())

    def test_owner_can_toggle_a_task(self):
        task = TodoTask.objects.create(goal=self.goal, title="Complete this")
        self.client.post(reverse("tracker:whoami"), {"action": "switch", "member_id": self.member.pk}, secure=True)
        response = self.client.post(reverse("tracker:task_toggle", args=[task.pk]), secure=True)
        self.assertRedirects(response, self.goal.get_absolute_url(), fetch_redirect_response=False)
        task.refresh_from_db()
        self.assertTrue(task.completed)

    def test_owner_can_add_a_task_with_a_deadline(self):
        self.client.post(reverse("tracker:whoami"), {"action": "switch", "member_id": self.member.pk}, secure=True)
        response = self.client.post(
            reverse("tracker:task_create", args=[self.goal.pk]),
            {"title": "Schedule inspection", "due_date": days(7)},
            secure=True,
        )
        self.assertRedirects(response, self.goal.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(self.goal.tasks.get().due_date, days(7))

    def test_reorder_cannot_move_another_members_goal(self):
        other = Member.objects.create(name="Other")
        others_goal = Goal.objects.create(
            board=self.board, owner=other, title="Not yours",
            start_date=days(-5), end_date=days(5), status=Goal.STATUS_NOT_STARTED,
        )
        self.client.post(reverse("tracker:whoami"), {"action": "switch", "member_id": self.member.pk}, secure=True)
        response = self.client.post(
            reverse("tracker:goal_reorder"),
            data=json.dumps({
                "scope": "board",
                "scope_id": str(self.board.pk),
                "columns": {"completed": [str(others_goal.pk)]},
            }),
            content_type="application/json",
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        others_goal.refresh_from_db()
        self.assertEqual(others_goal.status, Goal.STATUS_NOT_STARTED)


class CategoryTests(TestCase):
    def test_create_category_requires_a_member(self):
        board = GoalBoard.objects.create(name="Board")
        category_url = reverse("tracker:category_list", args=[board.pk])
        response = self.client.get(category_url, secure=True)
        self.assertRedirects(
            response,
            f"{reverse('tracker:whoami')}?next={category_url}",
            fetch_redirect_response=False,
        )

    def test_member_can_create_category(self):
        member = Member.objects.create(name="Alex")
        board = GoalBoard.objects.create(name="Board", created_by=member)
        self.client.post(reverse("tracker:whoami"), {"action": "switch", "member_id": member.pk}, secure=True)
        response = self.client.post(
            reverse("tracker:category_list", args=[board.pk]), {"name": "Side Project", "color": "#7B6DCC"}, secure=True
        )
        self.assertEqual(response.status_code, 302)
        category = Category.objects.get(board=board, name="Side Project")
        self.assertEqual(category.color, "#7B6DCC")
        self.assertEqual(category.created_by, member)


class BoardFilterTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Alex")
        self.other = Member.objects.create(name="Sam")
        self.board = GoalBoard.objects.create(name="Board")
        self.finance = Category.objects.create(board=self.board, name="Test Finance", color="#4F7A62")
        self.health = Category.objects.create(board=self.board, name="Test Health", color="#E6A65D")
        self.goal_a = Goal.objects.create(
            board=self.board, owner=self.member, title="Save money",
            category=self.finance, start_date=days(-5), end_date=days(5),
        )
        self.goal_b = Goal.objects.create(
            board=self.board, owner=self.other, title="Run a marathon",
            category=self.health, start_date=days(-5), end_date=days(5),
        )

    def test_filter_by_category(self):
        url = reverse("tracker:board_detail", args=[self.board.pk]) + f"?category={self.finance.pk}"
        response = self.client.get(url, secure=True)
        self.assertContains(response, "Save money")
        self.assertNotContains(response, "Run a marathon")

    def test_filter_by_owner(self):
        url = reverse("tracker:board_detail", args=[self.board.pk]) + f"?owner={self.other.pk}"
        response = self.client.get(url, secure=True)
        self.assertContains(response, "Run a marathon")
        self.assertNotContains(response, "Save money")

    def test_filter_by_keyword(self):
        url = reverse("tracker:board_detail", args=[self.board.pk]) + "?q=marathon"
        response = self.client.get(url, secure=True)
        self.assertContains(response, "Run a marathon")
        self.assertNotContains(response, "Save money")


class GoalImportExportTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Alex")
        self.board = GoalBoard.objects.create(name="Board", created_by=self.member)
        self.category = Category.objects.create(board=self.board, name="Test Finance", color="#4F7A62")
        self.goal = Goal.objects.create(
            board=self.board, owner=self.member, title="Save $10,000", category=self.category,
            start_date=days(-10), end_date=days(90), progress_percent=40,
        )
        TodoTask.objects.create(goal=self.goal, title="Save first $5,000", completed=True, due_date=days(30))

    def test_export_includes_tasks(self):
        data = goal_io.export_board(self.board)
        self.assertEqual(len(data["goals"]), 1)
        self.assertEqual(data["goals"][0]["title"], "Save $10,000")
        self.assertEqual(data["goals"][0]["tasks"], [{"title": "Save first $5,000", "completed": True, "due_date": days(30).isoformat()}])

    def test_import_round_trip_recreates_goal_and_tasks(self):
        data = goal_io.export_board(self.board)
        other_board = GoalBoard.objects.create(name="Other Board")
        created = goal_io.import_goals(other_board, data, default_owner=self.member)
        self.assertEqual(created, 1)
        top = other_board.top_level_goals.get()
        self.assertEqual(top.title, "Save $10,000")
        self.assertEqual(top.category.name, "Test Finance")
        self.assertEqual(top.tasks.get().title, "Save first $5,000")
        self.assertEqual(top.tasks.get().due_date, days(30))

    def test_import_rejects_missing_title(self):
        with self.assertRaises(goal_io.GoalImportError):
            goal_io.import_goals(self.board, {"goals": [{"status": "in_progress"}]}, default_owner=self.member)

    def test_import_ignores_spoofed_owner_and_uses_importer(self):
        victim = Member.objects.create(name="Victim")
        data = {"goals": [{"title": "Not really mine", "owner": "Victim", "status": "not_started"}]}
        goal_io.import_goals(self.board, data, default_owner=self.member)
        goal = Goal.objects.get(title="Not really mine")
        self.assertEqual(goal.owner, self.member)
        self.assertNotEqual(goal.owner, victim)

    def test_import_view_end_to_end(self):
        self.client.post(reverse("tracker:whoami"), {"action": "switch", "member_id": self.member.pk}, secure=True)
        export_response = self.client.get(
            reverse("tracker:board_export_json", args=[self.board.pk]), secure=True
        )
        new_board = GoalBoard.objects.create(name="Fresh Board", created_by=self.member)
        response = self.client.post(
            reverse("tracker:board_import_json", args=[new_board.pk]),
            {"file": SimpleUploadedFile("goals.json", export_response.content, content_type="application/json")},
            secure=True,
        )
        self.assertRedirects(response, new_board.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(new_board.top_level_goals.count(), 1)
