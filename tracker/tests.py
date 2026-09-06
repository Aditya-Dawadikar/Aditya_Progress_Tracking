import datetime
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Goal, GoalBoard, Member
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
