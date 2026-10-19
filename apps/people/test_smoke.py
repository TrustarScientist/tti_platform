"""
command to run before git push: python -m pyflakes apps; python manage.py test apps.people.test_smoke --settings=tti_platform.settings_test
"""

# apps/people/test_smoke.py
from datetime import datetime, time, timedelta, date

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import TUser
from .billing import issue_invoice, previous_month
from .models import (Assessment, Attempt, ClassSession, Cohort, Enrollment, Lesson,
                     Student, StudentGuardian, Track, TRSDimension, TRSScore, Price, Payment)
from .services import consistency_score, price_for
import hashlib
import hmac
import json
from unittest import mock



PASSWORD = 'pw-12345-test'
ACTIVE, COHORT, SELF_PACED = Enrollment.Status.ACTIVE, Enrollment.DeliveryMode.COHORT, Enrollment.DeliveryMode.SELF_PACED


def make_user(email, role, **extra):
    return TUser.objects.create_user(
        email=email, password=PASSWORD, role=role, status=TUser.Status.APPROVED,
        first_name=email.split('@')[0].title(), last_name='Tester', **extra)


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.knowledge = TRSDimension.objects.create(code='knowledge', name='Knowledge', order=0)
        TRSDimension.objects.create(code='consistency', name='Consistency', order=1)

        cls.admin = TUser.objects.create_superuser(email='admin@example.com', password=PASSWORD)
        cls.parent = make_user('parent@example.com', TUser.Role.PARENT)
        cls.other_parent = make_user('otherparent@example.com', TUser.Role.PARENT)
        cls.partner = make_user('partner@example.com', TUser.Role.SCHOOL_PARTNER, school_name='Rockgold Test')
        cls.other_partner = make_user('partner2@example.com', TUser.Role.SCHOOL_PARTNER, school_name='Another School')
        cls.instructor = make_user('teacher@example.com', TUser.Role.INSTRUCTOR)
        cls.stranger_instructor = make_user('teacher2@example.com', TUser.Role.INSTRUCTOR)
        cls.student_user = make_user('student@example.com', TUser.Role.STUDENT)
        cls.school = cls.partner.school

        cls.track = Track.objects.create(name='Foundations', price_naira=15000)
        cls.l1 = Lesson.objects.create(track=cls.track, position=1, title='Meet the screen')
        cls.l2 = Lesson.objects.create(track=cls.track, position=2, title='Tap and drag')
        cls.assessment = Assessment.objects.create(
            track=cls.track, lesson=cls.l1, dimension=cls.knowledge, title='Check-in',
            assessment_type=Assessment.Type.EXERCISE, requires_manual_review=True)
        cls.public_cohort = Cohort.objects.create(track=cls.track, name='Public B1')
        cls.public_cohort.instructors.add(cls.instructor)

        cls.school_track = Track.objects.create(name='CNS Rockgold', audience=Track.Audience.SCHOOL, price_naira=5000)
        Lesson.objects.create(track=cls.school_track, position=1, title='What is coding')
        cls.school_cohort = Cohort.objects.create(track=cls.school_track, name='Rockgold Term 1',
                                                  school=cls.school, capacity=3)

        cls.child = Student.objects.create(first_name='Tobi', last_name='Ade')  # no login
        StudentGuardian.objects.create(student=cls.child, guardian=cls.parent,
                                       relationship=StudentGuardian.Relationship.PARENT)
        cls.stranger_child = Student.objects.create(first_name='Zed', last_name='Other')
        StudentGuardian.objects.create(student=cls.stranger_child, guardian=cls.other_parent,
                                       relationship=StudentGuardian.Relationship.PARENT)
        cls.own_student = Student.objects.create(user=cls.student_user, first_name='Sam', last_name='Solo')

        cls.child_enrollment = Enrollment.objects.create(
            student=cls.child, track=cls.track, delivery_mode=COHORT, cohort=cls.public_cohort,
            status=ACTIVE, activated_at=now, enrolled_by=cls.parent)
        cls.own_enrollment = Enrollment.objects.create(
            student=cls.own_student, track=cls.track, delivery_mode=SELF_PACED,
            status=ACTIVE, activated_at=now, enrolled_by=cls.student_user)

    def assertPage(self, user, name, args=(), code=200):
        self.client.force_login(user)
        resp = self.client.get(reverse(name, args=args))
        self.assertEqual(resp.status_code, code, f"{user.email} -> {name}")
        return resp


class PageTests(Base):
    def test_public_pages_load(self):
        for name in ('index', 'login', 'signup', 'healthz'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_anonymous_visitors_are_sent_to_login(self):
        for url in (reverse('dashboard'), reverse('student-add'), reverse('teach-home'),
                    reverse('student-enroll', args=[self.child.pk])):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, url)
            self.assertIn('/login/', resp['Location'], url)

    def test_login_by_email(self):
        resp = self.client.post(reverse('login'), {'username': 'parent@example.com', 'password': PASSWORD})
        self.assertRedirects(resp, reverse('dashboard'), fetch_redirect_response=False)

    def test_each_role_can_open_its_pages(self):
        child, own = self.child.pk, self.own_student.pk
        cases = [
            (self.admin, 'dashboard', ()), (self.admin, 'teach-home', ()),
            (self.parent, 'dashboard', ()), (self.parent, 'student-add', ()), (self.parent, 'student-link-child', ()),
            (self.parent, 'student-enroll', (child,)),
            (self.parent, 'student-enroll-delivery', (child, self.track.pk)),
            (self.parent, 'student-lesson', (self.child_enrollment.pk,)),
            (self.parent, 'student-trs-profile', (child,)),
            (self.partner, 'dashboard', ()), (self.partner, 'student-bulk-roster', ()),
            (self.student_user, 'dashboard', ()), (self.student_user, 'student-enroll', (own,)),
            (self.student_user, 'student-lesson', (self.own_enrollment.pk,)),
            (self.student_user, 'student-trs-profile', (own,)),
            (self.student_user, 'student-submit-assessment', (self.own_enrollment.pk, self.assessment.pk)),
            (self.instructor, 'teach-home', ()), (self.instructor, 'teach-cohort', (self.public_cohort.pk,)),
            (self.instructor, 'teach-attendance', (self.public_cohort.pk,)),
        ]
        for user, name, args in cases:
            self.assertPage(user, name, args)

    def test_instructor_dashboard_redirects_to_console(self):
        self.client.force_login(self.instructor)
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('teach-home'))


class AccessTests(Base):
    def test_parent_cannot_reach_another_familys_child(self):
        other = Enrollment.objects.create(student=self.stranger_child, track=self.track,
                                          delivery_mode=SELF_PACED, status=ACTIVE, activated_at=timezone.now())
        self.client.force_login(self.parent)
        for name, args in (('student-enroll', (self.stranger_child.pk,)),
                           ('student-trs-profile', (self.stranger_child.pk,)),
                           ('student-lesson', (other.pk,))):
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403, name)

    def test_staff_only_pages_are_closed_to_others(self):
        self.assertPage(self.parent, 'student-bulk-roster', (), 403)
        self.assertPage(self.parent, 'teach-home', (), 403)
        self.assertPage(self.student_user, 'student-enroll', (self.child.pk,), 403)

    def test_school_programme_is_hidden_from_public_and_other_schools(self):
        url = reverse('student-enroll-delivery', args=[self.child.pk, self.school_track.pk])
        for user in (self.parent, self.other_partner):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 404, user.email)

    def test_school_sees_only_its_cohort_and_enrolls_straight_to_active(self):
        kid = Student.objects.create(first_name='Rock', last_name='Kid')
        StudentGuardian.objects.create(student=kid, guardian=self.partner,
                                       relationship=StudentGuardian.Relationship.SCHOOL_PARTNER)
        url = reverse('student-enroll-delivery', args=[kid.pk, self.school_track.pk])
        self.client.force_login(self.partner)
        page = self.client.get(url)
        self.assertContains(page, 'Rockgold Term 1')
        self.assertNotContains(page, 'Self-paced')
        self.client.post(url, {'delivery': f'cohort:{self.school_cohort.pk}'})
        e = Enrollment.objects.get(student=kid, track=self.school_track)
        self.assertEqual((e.status, e.billed_to, e.school_id), (ACTIVE, Enrollment.BilledTo.SCHOOL, self.school.pk))

    def test_approved_partner_gets_a_school_and_reuses_it_by_name(self):
        self.assertEqual(self.partner.school.name, 'Rockgold Test')
        twin = make_user('twin@example.com', TUser.Role.SCHOOL_PARTNER, school_name='ROCKGOLD test')
        self.assertEqual(twin.school_id, self.partner.school_id)

    def test_guardian_acts_for_a_child_without_login_but_not_one_with_login(self):
        self.client.force_login(self.parent)
        url = reverse('student-submit-assessment', args=[self.child_enrollment.pk, self.assessment.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {'notes': 'answer typed by parent'})
        self.assertEqual(Attempt.objects.get(enrollment=self.child_enrollment).submitted_by, self.parent)

        StudentGuardian.objects.create(student=self.own_student, guardian=self.other_parent,
                                       relationship=StudentGuardian.Relationship.PARENT)
        self.client.force_login(self.other_parent)
        own_url = reverse('student-submit-assessment', args=[self.own_enrollment.pk, self.assessment.pk])
        self.assertEqual(self.client.get(own_url).status_code, 403)

    def test_parent_invite_code_links_a_school_added_child_once(self):
        kid = Student.objects.create(first_name='Kemi', last_name='Bello')
        StudentGuardian.objects.create(student=kid, guardian=self.partner,
                                       relationship=StudentGuardian.Relationship.SCHOOL_PARTNER)
        self.client.force_login(self.partner)
        self.client.post(reverse('student-generate-guardian-invite', args=[kid.pk]))
        kid.refresh_from_db()
        code = kid.guardian_invite_code
        self.assertTrue(code)

        self.client.force_login(self.other_parent)
        self.client.post(reverse('student-link-child'), {'code': code})
        self.assertTrue(StudentGuardian.objects.filter(student=kid, guardian=self.other_parent).exists())

        self.client.force_login(self.parent)
        self.client.post(reverse('student-link-child'), {'code': code})
        self.assertFalse(StudentGuardian.objects.filter(student=kid, guardian=self.parent).exists())


class TeachingTests(Base):
    def test_unassigned_instructor_is_blocked(self):
        self.client.force_login(self.stranger_instructor)
        for name in ('teach-cohort', 'teach-cohort-advance', 'teach-attendance'):
            url = reverse(name, args=[self.public_cohort.pk])
            self.assertEqual(self.client.get(url).status_code if name != 'teach-cohort-advance'
                             else self.client.post(url).status_code, 403, name)

    def test_advance_works_with_blank_pointer_and_completes_the_batch(self):
        self.client.force_login(self.instructor)
        url = reverse('teach-cohort-advance', args=[self.public_cohort.pk])
        self.assertIsNone(self.public_cohort.current_lesson_id)
        self.client.post(url)
        self.public_cohort.refresh_from_db()
        self.assertEqual(self.public_cohort.current_lesson_id, self.l2.pk)
        self.client.post(url)  # that was the last lesson
        self.child_enrollment.refresh_from_db()
        self.assertEqual(self.child_enrollment.status, Enrollment.Status.COMPLETED)
        self.assertIsNotNone(self.child_enrollment.ended_at)

    def test_review_keeps_the_students_answer(self):
        attempt = Attempt.objects.create(enrollment=self.child_enrollment, assessment=self.assessment,
                                         status=Attempt.Status.NEEDS_REVIEW, notes='my own answer')
        self.client.force_login(self.instructor)
        url = reverse('teach-attempt-review', args=[attempt.pk])
        self.client.post(url, {'action': 'verify', 'score': '150'})  # out of range: refused
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.NEEDS_REVIEW)
        self.client.post(url, {'action': 'verify', 'score': '80', 'feedback': 'Well done'})
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.score, attempt.notes, attempt.feedback),
                         (Attempt.Status.VERIFIED, 80, 'my own answer', 'Well done'))
        self.assertEqual(TRSScore.objects.get(student=self.child, dimension=self.knowledge).score, 80)

    def test_attendance_feeds_consistency_and_ignores_excused(self):
        self.client.force_login(self.instructor)
        url = reverse('teach-attendance', args=[self.public_cohort.pk])
        key = f'status_{self.child_enrollment.pk}'
        today = timezone.localdate()
        for days_ago, status in ((0, 'PRESENT'), (1, 'ABSENT'), (2, 'EXCUSED')):
            day = today - timedelta(days=days_ago)
            self.client.post(url, {'date': day.isoformat(), 'topic': 'x', key: status})
        self.assertEqual(ClassSession.objects.filter(cohort=self.public_cohort).count(), 3)
        self.assertEqual(consistency_score(self.child), 50)
        self.client.post(url, {'date': (today + timedelta(days=1)).isoformat(), key: 'PRESENT'})
        self.assertEqual(ClassSession.objects.filter(cohort=self.public_cohort).count(), 3)  # future refused


class MoneyTests(Base):
    def _invoice(self):
        kid = Student.objects.create(first_name='Bill', last_name='Able')
        when = timezone.make_aware(datetime.combine(previous_month().replace(day=15), time(12, 0)))
        Enrollment.objects.create(student=kid, track=self.school_track, delivery_mode=COHORT,
                                  cohort=self.school_cohort, status=ACTIVE, activated_at=when,
                                  enrolled_by=self.partner, school=self.school,
                                  billed_to=Enrollment.BilledTo.SCHOOL)
        return issue_invoice(self.school, previous_month())

    def test_invoice_is_issued_once_with_the_right_total(self):
        invoice, created = self._invoice()
        self.assertTrue(created)
        self.assertEqual((invoice.student_count, invoice.amount_naira), (1, 5000))
        again, created_again = issue_invoice(self.school, previous_month())
        self.assertFalse(created_again)
        self.assertEqual(again.pk, invoice.pk)

    def test_invoice_is_visible_to_its_school_and_staff_only(self):
        invoice, _ = self._invoice()
        for user, code in ((self.partner, 200), (self.admin, 200), (self.other_partner, 403), (self.parent, 403)):
            self.assertPage(user, 'invoice-detail', (invoice.pk,), code)

    def test_bulk_roster_previews_then_confirms_and_respects_seats(self):
        self.client.force_login(self.partner)
        url = reverse('student-bulk-roster')
        data = {'cohort': self.school_cohort.pk, 'names': 'Ada Obi\nChidi Eze\nAda Obi'}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertEqual(Student.objects.filter(first_name='Ada').count(), 0)  # preview saves nothing
        self.client.post(url, {**data, 'confirm': '1'})
        billed = Enrollment.objects.filter(cohort=self.school_cohort, billed_to=Enrollment.BilledTo.SCHOOL)
        self.assertEqual(billed.count(), 2)
        self.client.post(url, {**data, 'confirm': '1'})  # re-running adds nobody
        self.assertEqual(billed.count(), 2)
        too_many = {'cohort': self.school_cohort.pk, 'names': 'A One\nB Two\nC Three\nD Four', 'confirm': '1'}
        self.client.post(url, too_many)
        self.assertEqual(billed.count(), 2)  # only 1 seat was left

    def test_ended_at_follows_status(self):
        e = self.own_enrollment
        e.status = Enrollment.Status.COMPLETED
        e.save()
        self.assertIsNotNone(e.ended_at)
        e.status = ACTIVE
        e.save()
        self.assertIsNone(e.ended_at)



class PriceBookTests(Base):
    def test_latest_effective_price_wins_and_inactive_or_future_are_ignored(self):
        today = timezone.localdate()
        for amount, days, active in ((3000, -60, True), (4000, -1, True), (5000, 30, True), (9999, 0, False)):
            Price.objects.create(track=self.track, delivery_mode=SELF_PACED, amount=amount,
                                 effective_from=today + timedelta(days=days), is_active=active)
        price = price_for(self.track, SELF_PACED)
        self.assertEqual(price.amount, 4000)
        self.assertEqual(price.amount_minor, 400000)
        self.assertIsNone(price_for(self.track, SELF_PACED, region='UK'))

    def test_delivery_step_shows_the_price_for_each_format(self):
        Price.objects.create(track=self.track, delivery_mode=SELF_PACED, amount=4000)
        self.client.force_login(self.parent)
        page = self.client.get(reverse('student-enroll-delivery', args=[self.child.pk, self.track.pk]))
        self.assertContains(page, '₦4,000 / month')



    def test_track_step_shows_no_price(self):
        Price.objects.create(track=self.track, delivery_mode=SELF_PACED, amount=4000)
        kid = Student.objects.create(first_name='New', last_name='Kid')
        StudentGuardian.objects.create(student=kid, guardian=self.parent,
                                       relationship=StudentGuardian.Relationship.PARENT)
        self.client.force_login(self.parent)
        page = self.client.get(reverse('student-enroll', args=[kid.pk]))
        self.assertContains(page, 'Foundations')
        self.assertNotContains(page, '₦')
        self.assertNotContains(page, '8358')  # the old hard-coded track price

    def test_newer_price_replaces_older_on_the_delivery_step(self):
        today = timezone.localdate()
        Price.objects.create(track=self.track, delivery_mode=SELF_PACED, amount=3000,
                             effective_from=today - timedelta(days=30))
        self.client.force_login(self.parent)
        url = reverse('student-enroll-delivery', args=[self.child.pk, self.track.pk])
        self.assertContains(self.client.get(url), '₦3,000 / month')
        Price.objects.create(track=self.track, delivery_mode=SELF_PACED, amount=4000, effective_from=today)
        page = self.client.get(url)
        self.assertContains(page, '₦4,000 / month')
        self.assertNotContains(page, '₦3,000')


@override_settings(PAYSTACK_SECRET_KEY='sk_test_unit', ACCESS_GRACE_DAYS=3)
class PaymentTests(Base):
    def setUp(self):
        Price.objects.create(track=self.track, delivery_mode=SELF_PACED, amount=4000)
        self.kid = Student.objects.create(first_name='Pay', last_name='Kid')
        StudentGuardian.objects.create(student=self.kid, guardian=self.parent,
                                       relationship=StudentGuardian.Relationship.PARENT)
        self.enrollment = Enrollment.objects.create(
            student=self.kid, track=self.track, delivery_mode=SELF_PACED, enrolled_by=self.parent)

    def _webhook(self, reference='TTI-TEST1', amount_minor=400000, secret='sk_test_unit'):
        Payment.objects.get_or_create(reference=reference, defaults=dict(
            enrollment=self.enrollment, amount=4000, currency='NGN', access_days=30))
        raw = json.dumps({'event': 'charge.success', 'data': {
            'reference': reference, 'amount': amount_minor, 'currency': 'NGN', 'status': 'success'}}).encode()
        signature = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
        return self.client.post(reverse('pay-webhook'), data=raw, content_type='application/json',
                                HTTP_X_PAYSTACK_SIGNATURE=signature)

    @mock.patch('apps.people.payments.initialize_transaction')
    def test_checkout_charges_the_price_book_amount_not_the_browser(self, init):
        init.return_value = {'authorization_url': 'https://checkout.paystack.com/abc'}
        self.client.force_login(self.parent)
        resp = self.client.post(reverse('pay-checkout', args=[self.enrollment.pk]), {'amount': '1'})
        self.assertRedirects(resp, 'https://checkout.paystack.com/abc', fetch_redirect_response=False)
        payment = Payment.objects.get(enrollment=self.enrollment)
        self.assertEqual((payment.amount, payment.status), (4000, Payment.Status.PENDING))
        self.assertEqual(init.call_args.kwargs['amount_minor'], 400000)

    def test_only_a_guardian_can_start_checkout(self):
        self.client.force_login(self.other_parent)
        resp = self.client.post(reverse('pay-checkout', args=[self.enrollment.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_webhook_activates_once_and_ignores_replays(self):
        self.assertEqual(self._webhook().status_code, 200)
        self.enrollment.refresh_from_db()
        expected = timezone.localdate() + timedelta(days=30)
        self.assertEqual((self.enrollment.status, self.enrollment.paid_through), (ACTIVE, expected))
        self._webhook()  # Paystack retries; nothing may change
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.paid_through, expected)
        self.assertEqual(Payment.objects.get(reference='TTI-TEST1').status, Payment.Status.PAID)

    def test_webhook_rejects_a_bad_signature(self):
        self.assertEqual(self._webhook(secret='someone-elses-key').status_code, 401)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.PENDING_PAYMENT)

    def test_wrong_amount_is_held_for_review_not_activated(self):
        self._webhook(amount_minor=100)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.PENDING_PAYMENT)
        self.assertEqual(Payment.objects.get(reference='TTI-TEST1').status, Payment.Status.REVIEW)

    @mock.patch('apps.people.payments.verify_transaction')
    def test_return_visit_verifies_with_paystack_and_activates(self, verify):
        Payment.objects.create(enrollment=self.enrollment, reference='TTI-CB1', amount=4000,
                               currency='NGN', access_days=30)
        verify.return_value = {'status': 'success', 'amount': 400000, 'currency': 'NGN'}
        self.client.force_login(self.parent)
        self.client.get(reverse('pay-callback'), {'reference': 'TTI-CB1'})
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, ACTIVE)

    def test_renewal_extends_from_the_later_date(self):
        self.enrollment.status = ACTIVE
        self.enrollment.paid_through = timezone.localdate() + timedelta(days=10)
        self.enrollment.save()
        self._webhook()
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.paid_through, timezone.localdate() + timedelta(days=40))

    def test_grace_period_then_pause(self):
        e = self.enrollment
        e.status, e.paid_through = ACTIVE, date(2026, 10, 1)
        self.assertTrue(e.has_access(date(2026, 10, 4)))     # inside the 3 grace days
        self.assertFalse(e.has_access(date(2026, 10, 5)))
        e.billed_to = Enrollment.BilledTo.SCHOOL
        self.assertTrue(e.has_access(date(2030, 1, 1)))      # school-billed never pauses

    def test_lapsed_enrollment_shows_payment_due_and_hides_the_lesson(self):
        self.enrollment.status = ACTIVE
        self.enrollment.billed_to = Enrollment.BilledTo.FAMILY  # <-- ADD THIS LINE
        self.enrollment.paid_through = timezone.localdate() - timedelta(days=10)
        self.enrollment.save()
        
        self.client.force_login(self.parent)
        page = self.client.get(reverse('student-lesson', args=[self.enrollment.pk]))
        
        self.assertContains(page, 'Payment due')
        self.assertContains(page, 'Pay ₦4,000') # Tip: simplify assertion to match 'Pay ' or '4,000' if formatting differs
        self.assertNotContains(page, 'Meet the screen')