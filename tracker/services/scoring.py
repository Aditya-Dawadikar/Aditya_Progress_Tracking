"""Cross-member leaderboard scoring.

A member's leaderboard score is the average `pace_score` (see
Goal.pace_score) across their top-level goals that haven't been abandoned.
pace_score is already normalized to 0-100 regardless of a goal's own
duration or progress scale, so it's directly comparable across members with
completely different goals. Goals without both a start and end date have no
pace_score (there's no deadline to be "on pace" against) and are excluded.
"""
from tracker.models import Goal, Member


def member_leaderboard():
    """Return Members ordered by score (desc), each annotated with:
    .score (float|None), .active_goal_count, .completed_goal_count.
    Members with no scoreable goals sort last with score=None.
    """
    rows = []
    for member in Member.objects.all():
        top_level = member.goals.filter(parent__isnull=True).exclude(status=Goal.STATUS_ABANDONED)
        scores = [s for s in (g.pace_score for g in top_level) if s is not None]
        member.score = round(sum(scores) / len(scores), 1) if scores else None
        member.active_goal_count = top_level.exclude(status=Goal.STATUS_COMPLETED).count()
        member.completed_goal_count = top_level.filter(status=Goal.STATUS_COMPLETED).count()
        rows.append(member)
    rows.sort(key=lambda m: (m.score is None, -(m.score or 0)))
    return rows
