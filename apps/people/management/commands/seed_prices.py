# apps/people/management/commands/seed_prices.py
from django.core.management.base import BaseCommand

from apps.people.models import Enrollment, Price, Track

C = Enrollment.DeliveryMode.COHORT
O = Enrollment.DeliveryMode.ONE_ON_ONE
S = Enrollment.DeliveryMode.SELF_PACED

STARTER = {
    'Foundations': {C: 10000, S: 4000, O: 40000},
    'Explorers': {C: 10000, S: 4000, O: 40000},
    'Builders': {C: 10000, S: 4000, O: 45000},
    'Engineers': {C: 10000, S: 4000, O: 50000},
}


class Command(BaseCommand):
    help = "Create starter NGN prices for the four public tracks. Never overwrites an existing price."

    def handle(self, *args, **options):
        for name, modes in STARTER.items():
            track = Track.objects.filter(name__iexact=name).first()
            if track is None:
                self.stdout.write(f"Skipped {name}: no track with that name.")
                continue
            for mode, amount in modes.items():
                if Price.objects.filter(track=track, delivery_mode=mode, region='NG', currency='NGN').exists():
                    continue
                Price.objects.create(track=track, delivery_mode=mode, amount=amount, note="Starter price")
                self.stdout.write(f"Created {name} · {mode} · ₦{amount:,}")