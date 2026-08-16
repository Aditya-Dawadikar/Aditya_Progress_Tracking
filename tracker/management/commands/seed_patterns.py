from django.core.management.base import BaseCommand

from tracker.models import Pattern

PATTERNS = [
    "Arrays",
    "Hashing",
    "Two Pointers",
    "Sliding Window",
    "Binary Search",
    "Prefix Sum",
    "Stack",
    "Monotonic Stack",
    "Heap",
    "Intervals",
    "Greedy",
    "Trees",
    "BST",
    "Graphs",
    "BFS",
    "DFS",
    "Topological Sort",
    "Union Find",
    "Backtracking",
    "Dynamic Programming",
    "1D DP",
    "2D DP",
    "Trie",
    "Bit Manipulation",
    "Math",
    "Geometry",
    "Linked List",
]


class Command(BaseCommand):
    help = "Seed the Pattern catalog with common LeetCode algorithmic patterns."

    def handle(self, *args, **options):
        created = 0
        for name in PATTERNS:
            _, was_created = Pattern.objects.get_or_create(name=name)
            if was_created:
                created += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded patterns: {created} created, {len(PATTERNS) - created} already existed."
            )
        )
