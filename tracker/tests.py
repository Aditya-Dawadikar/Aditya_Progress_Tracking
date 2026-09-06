import datetime
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Category, Goal, GoalBoard, Member
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

    def test_effective_progress_rolls_up_from_subgoals(self):
        parent = self.make_goal(title="Parent")
        self.make_goal(title="Child A", parent=parent, progress_percent=100)
        self.make_goal(title="Child B", parent=parent, progress_percent=50)
        self.assertEqual(parent.effective_progress, 75)

    def test_subgoal_inherits_parent_board(self):
        other_board = GoalBoard.objects.create(name="Other")
        parent = self.make_goal(title="Parent")
        child = Goal.objects.create(
            board=other_board, parent=parent, owner=self.member, title="Child",
            start_date=days(-5), end_date=days(5),
        )
        self.assertEqual(child.board_id, parent.board_id)

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
        self.assertEqual(self.client.session["member_id"], Member.objects.get(name="New Person").pk)

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
                "scope_id": self.board.pk,
                "columns": {"in_progress": [second.pk, self.goal.pk]},
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

    def test_cannot_add_subgoal_to_another_members_goal(self):
        other = Member.objects.create(name="Other")
        self.client.post(reverse("tracker:whoami"), {"action": "switch", "member_id": other.pk}, secure=True)
        url = reverse("tracker:goal_create") + f"?parent={self.goal.pk}"
        response = self.client.post(url, {
            "title": "Sneaky subgoal", "category": "", "start_date": days(-1), "end_date": days(1),
            "status": Goal.STATUS_NOT_STARTED, "progress_percent": 0,
        }, secure=True)
        self.assertRedirects(response, self.goal.get_absolute_url(), fetch_redirect_response=False)
        self.assertFalse(self.goal.subgoals.exists())

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
                "scope_id": self.board.pk,
                "columns": {"completed": [others_goal.pk]},
            }),
            content_type="application/json",
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        others_goal.refresh_from_db()
        self.assertEqual(others_goal.status, Goal.STATUS_NOT_STARTED)


class CategoryTests(TestCase):
    def test_create_category_requires_a_member(self):
        response = self.client.get(reverse("tracker:category_list"), secure=True)
        self.assertRedirects(
            response,
            f"{reverse('tracker:whoami')}?next={reverse('tracker:category_list')}",
            fetch_redirect_response=False,
        )

    def test_member_can_create_category(self):
        member = Member.objects.create(name="Alex")
        self.client.post(reverse("tracker:whoami"), {"action": "switch", "member_id": member.pk}, secure=True)
        response = self.client.post(
            reverse("tracker:category_list"), {"name": "Side Project", "color": "#7B6DCC"}, secure=True
        )
        self.assertEqual(response.status_code, 302)
        category = Category.objects.get(name="Side Project")
        self.assertEqual(category.color, "#7B6DCC")
        self.assertEqual(category.created_by, member)


class BoardFilterTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Alex")
        self.other = Member.objects.create(name="Sam")
        self.board = GoalBoard.objects.create(name="Board")
        self.finance = Category.objects.create(name="Test Finance", color="#4F7A62")
        self.health = Category.objects.create(name="Test Health", color="#E6A65D")
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
        self.category = Category.objects.create(name="Test Finance", color="#4F7A62")
        self.parent = Goal.objects.create(
            board=self.board, owner=self.member, title="Save $10,000", category=self.category,
            start_date=days(-10), end_date=days(90), progress_percent=40,
        )
        Goal.objects.create(
            board=self.board, owner=self.member, title="First $5,000", parent=self.parent,
            start_date=days(-10), end_date=days(20), status=Goal.STATUS_COMPLETED, progress_percent=100,
        )

    def test_export_produces_nested_structure(self):
        data = goal_io.export_board(self.board)
        self.assertEqual(len(data["goals"]), 1)
        self.assertEqual(data["goals"][0]["title"], "Save $10,000")
        self.assertEqual(len(data["goals"][0]["subgoals"]), 1)
        self.assertEqual(data["goals"][0]["subgoals"][0]["title"], "First $5,000")

    def test_import_round_trip_recreates_goal_tree(self):
        data = goal_io.export_board(self.board)
        other_board = GoalBoard.objects.create(name="Other Board")
        created = goal_io.import_goals(other_board, data, default_owner=self.member)
        self.assertEqual(created, 2)
        top = other_board.top_level_goals.get()
        self.assertEqual(top.title, "Save $10,000")
        self.assertEqual(top.category.name, "Test Finance")
        self.assertEqual(top.subgoals.get().title, "First $5,000")

    def test_import_rejects_missing_title(self):
        with self.assertRaises(goal_io.GoalImportError):
            goal_io.import_goals(self.board, {"goals": [{"status": "in_progress"}]}, default_owner=self.member)

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
