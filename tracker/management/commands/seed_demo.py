import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.models import Goal, GoalBoard, Member


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

        def make_goal(owner, title, category, status, start_offset, end_offset, progress=0, parent=None, order=0):
            goal, created = Goal.objects.get_or_create(
                board=board,
                parent=parent,
                title=title,
                defaults=dict(
                    owner=owner,
                    category=category,
                    status=status,
                    start_date=today + datetime.timedelta(days=start_offset),
                    end_date=today + datetime.timedelta(days=end_offset),
                    progress_percent=progress,
                    order=order,
                ),
            )
            return goal

        # Alex: ahead of schedule, has subgoals.
        save = make_goal(alex, "Save $10,000", "Financial", Goal.STATUS_IN_PROGRESS, -60, 30, order=0)
        make_goal(alex, "Save first $5,000", "Financial", Goal.STATUS_COMPLETED, -60, -20, progress=100, parent=save, order=0)
        make_goal(alex, "Save next $5,000", "Financial", Goal.STATUS_IN_PROGRESS, -20, 30, progress=70, parent=save, order=1)

        # Sam: right on pace, no subgoals.
        make_goal(sam, "Run a 5k", "Health", Goal.STATUS_IN_PROGRESS, -30, 30, progress=48, order=0)

        # Jordan: behind schedule.
        make_goal(jordan, "Learn Spanish (A2)", "Learning", Goal.STATUS_IN_PROGRESS, -90, 10, progress=15, order=0)

        # A not-started and a completed goal for variety.
        make_goal(alex, "Read 12 books", "Personal", Goal.STATUS_NOT_STARTED, 5, 200, order=1)
        make_goal(sam, "Run a half marathon", "Health", Goal.STATUS_COMPLETED, -120, -10, progress=100, order=1)

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
