# apps/people/management/commands/link_partner_schools.py
from django.core.management.base import BaseCommand
from apps.accounts.models import TUser
from apps.people.models import School, Enrollment


class Command(BaseCommand):
    help = "Attach approved school partners to a School and backfill enrollment.school. Safe to re-run."

    def handle(self, *args, **options):
        linked = 0
        partners = TUser.objects.filter(
            role=TUser.Role.SCHOOL_PARTNER, status=TUser.Status.APPROVED, school__isnull=True
        ).exclude(school_name='')
        for partner in partners:
            name = partner.school_name.strip()
            school = School.objects.filter(name__iexact=name).first() or School.objects.create(
                name=name, contact_email=partner.email, contact_phone=partner.phone or '')
            partner.school = school
            partner.save(update_fields=['school'])
            linked += 1

        filled = 0
        for e in Enrollment.objects.filter(school__isnull=True, enrolled_by__school__isnull=False).select_related('enrolled_by'):
            e.school_id = e.enrolled_by.school_id
            e.save(update_fields=['school'])
            filled += 1
        self.stdout.write(f"Linked {linked} partner(s); backfilled {filled} enrollment(s).")