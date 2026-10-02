# apps/people/management/commands/seed_trs.py
from django.core.management.base import BaseCommand
from apps.people.models import TRSDimension

DIMENSIONS = [
    ("understanding", "Understanding", 20, "Grasping why, not just reciting what."),
    ("technique", "Technique", 20, "Correct hands-on execution of known methods."),
    ("problem-solving", "Problem-Solving", 20, "Reasoning through something unscripted."),
    ("creation", "Creation", 20, "A real artifact produced."),
    ("communication", "Communication", 10, "Explaining and presenting their own work."),
    ("conduct", "Conduct", 10, "Reliability, collaboration, taking feedback."),
]


class Command(BaseCommand):
    help = "Seed the six TRS dimensions. Safe to re-run — updates rather than duplicates."

    def handle(self, *args, **options):
        for i, (code, name, weight, desc) in enumerate(DIMENSIONS):
            obj, created = TRSDimension.objects.update_or_create(
                code=code,
                defaults={'name': name, 'default_weight': weight, 'description': desc, 'order': i},
            )
            self.stdout.write(f"{'Created' if created else 'Updated'}: {obj.name}")