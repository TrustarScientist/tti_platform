# apps/people/management/commands/seed_trs.py
from django.core.management.base import BaseCommand
from apps.people.models import TRSDimension

# seeds to start with, in case we need to reset the TRS dimensions. Safe to re-run — updates rather than duplicates.
DIMENSIONS = [
    ("knowledge", "Knowledge", "Quiz and assessment average."),
    ("craft", "Craft", "Instructor-rated quality of project work."),
    ("consistency", "Consistency", "Attendance and on-time submission, trailing 4 weeks."),
    ("communication", "Communication", "Instructor-rated at Show & Challenge / Demo Day checkpoints."),
    ("collaboration", "Collaboration", "Instructor-rated, informed by peer feedback."),
    ("delivery", "Delivery", "Snapshot of the current track's major deliverable."),
]


class Command(BaseCommand):
    help = "Seed the six locked TRS dimensions. Safe to re-run — updates rather than duplicates."

    def handle(self, *args, **options):
        for i, (code, name, desc) in enumerate(DIMENSIONS):
            obj, created = TRSDimension.objects.update_or_create(
                code=code, defaults={'name': name, 'description': desc, 'order': i},
            )
            self.stdout.write(f"{'Created' if created else 'Updated'}: {obj.name}")