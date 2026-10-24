# apps/people/management/commands/apply_price_book.py
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.people.models import Enrollment, Price, Track
from apps.people.services import price_for

C = Enrollment.DeliveryMode.COHORT
S = Enrollment.DeliveryMode.SELF_PACED
O = Enrollment.DeliveryMode.ONE_ON_ONE

# (format, plan_code, label shown to buyers, access days, naira)
SELF = [(S, 'MONTHLY', 'Monthly', 30, 4000), (S, 'QUARTERLY', '3 months, prepaid', 90, 10000)]
ONE = [(O, 'WEEKLY_1', '1 session a week', 28, 30000), (O, 'WEEKLY_2', '2 sessions a week', 28, 55000)]
BOOK = {
    'Foundations': [(C, 'MONTHLY', 'Monthly', 30, 10000)] + SELF + ONE,
    'Explorers': [(C, 'MONTHLY', 'Monthly', 30, 10000)] + SELF + ONE,
    'Builders': [(C, 'MONTHLY', 'Monthly', 30, 15000)] + SELF + ONE,
    'Engineers': [(C, 'MONTHLY', 'Monthly', 30, 20000)] + SELF + ONE,
}


class Command(BaseCommand):
    help = "Apply the approved naira price book (Oct 2026). Safe to re-run; keeps history."

    def handle(self, *args, **options):
        today = timezone.localdate()
        for name, plans in BOOK.items():
            track = Track.objects.filter(name__iexact=name).first()
            if track is None:
                self.stdout.write(f"Skipped {name}: no track with that name.")
                continue
            for mode, code, label, days, amount in plans:
                current = price_for(track, mode, 'NG', plan_code=code)
                if current and current.amount == amount and current.access_days == days:
                    continue
                _, created = Price.objects.update_or_create(
                    track=track, delivery_mode=mode, plan_code=code, region='NG', currency='NGN',
                    effective_from=today,
                    defaults={'amount': amount, 'access_days': days, 'plan_label': label,
                              'is_active': True, 'note': 'Price book Oct 2026'})
                self.stdout.write(f"{'Added' if created else 'Updated'} {name} · {mode} · {label}: ₦{amount:,}")
        retired = Price.objects.filter(delivery_mode=O, plan_code='MONTHLY', is_active=True).update(is_active=False)
        if retired:
            self.stdout.write(f"Retired {retired} old one-on-one price row(s).")