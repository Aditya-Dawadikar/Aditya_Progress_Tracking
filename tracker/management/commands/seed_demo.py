import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.models import CATEGORY_PALETTE, Category, Goal, GoalBoard, Member


class Command(BaseCommand):
    help = "Create demo members, boards, and goals for local verification."

    def handle(self, *args, **options):
        today = timezone.localdate()

        alex, _ = Member.objects.get_or_create(name="Alex")
        sam, _ = Member.objects.get_or_create(name="Sam")
        jordan, _ = Member.objects.get_or_create(name="Jordan")

        board, _ = GoalBoard.objects.get_or_create(
            name="2026 Goals",
            defaults={"description": "Personal goals for the year.", "created_by": alex},
        )
        for name, color in [("Financial", CATEGORY_PALETTE[0][0]), ("Health", CATEGORY_PALETTE[1][0]),
                             ("Career", CATEGORY_PALETTE[2][0]), ("Personal", CATEGORY_PALETTE[3][0]),
                             ("Learning", CATEGORY_PALETTE[5][0])]:
            Category.objects.get_or_create(board=board, name=name, defaults={"color": color})
        categories = {c.name: c for c in board.categories.all()}

        def make_goal(owner, title, category, status, start_offset=None, end_offset=None, progress=0, order=0):
            goal, created = Goal.objects.get_or_create(
                board=board,
                title=title,
                defaults=dict(
                    owner=owner,
                    category=categories.get(category),
                    status=status,
                    start_date=today + datetime.timedelta(days=start_offset) if start_offset is not None else None,
                    end_date=today + datetime.timedelta(days=end_offset) if end_offset is not None else None,
                    progress_percent=progress,
                    order=order,
                ),
            )
            return goal

        # Alex: ahead of schedule, with a focused task list.
        save = make_goal(alex, "Save $10,000", "Financial", Goal.STATUS_IN_PROGRESS, -60, 30, order=0)
        save.tasks.create(title="Save first $5,000", completed=True, order=0)
        save.tasks.create(title="Save next $5,000", completed=False, order=1)

        # Sam: right on pace, no tasks.
        make_goal(sam, "Run a 5k", "Health", Goal.STATUS_IN_PROGRESS, -30, 30, progress=48, order=0)

        # Jordan: behind schedule.
        make_goal(jordan, "Learn Spanish (A2)", "Learning", Goal.STATUS_IN_PROGRESS, -90, 10, progress=15, order=0)

        # A not-started and a completed goal for variety.
        make_goal(alex, "Read 12 books", "Personal", Goal.STATUS_NOT_STARTED, 5, 200, order=1)
        make_goal(sam, "Run a half marathon", "Health", Goal.STATUS_COMPLETED, -120, -10, progress=100, order=1)

        # No deadline — should show up with no gauge marker and stay off the leaderboard.
        make_goal(jordan, "Get better at cooking", "Personal", Goal.STATUS_IN_PROGRESS, progress=20, order=1)

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
