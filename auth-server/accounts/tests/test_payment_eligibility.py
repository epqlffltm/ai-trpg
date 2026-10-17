# auth-server/accounts/tests/test_payment_eligibility.py

"""
결제 자격을 결제 서버에 알리는 일(accounts/payment_eligibility.py)을 검증한다.

결제 서버를 부르는 함수는 대부분 가짜로 바꿔 끼운다. 이 파일이 보는 것은 "무엇을 언제 보내고 결과를 어떻게 적는가"다.
요청의 모양은 test_billing_client.py 가 본다.
"""

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.billing_client import APPLIED, BillingUnavailableError
from accounts.identity import verify_identity
from accounts.models import GuardianConsent, GuardianConsentStatus, PaymentEligibility, User
from accounts.payment_eligibility import (
    FIRST_RETRY_DELAY,
    LEASE,
    _claim_next,
    _mark_delivered,
    deliver_due_eligibility,
    mark_changed,
)
from accounts.tests.billing_stub import SECRET
from accounts.tests.helpers import ADULT_BIRTH_DATE, identity_token

MINOR_BIRTH_DATE = date(2010, 6, 1)


def make_user(number: int = 1) -> User:
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
    )


def verified(number: int = 1, birth_date: date = ADULT_BIRTH_DATE) -> User:
    user = make_user(number)
    verify_identity(user=user, token=identity_token(f'person-{number}', birth_date))
    return user


def row_of(user: User) -> PaymentEligibility:
    return PaymentEligibility.objects.get(user=user)


def at(moment):
    """결제 자격 쪽의 시계를 moment 로 맞춘다."""
    return patch('accounts.payment_eligibility.timezone.now', return_value=moment)


def billing_answers(*outcomes):
    """결제 서버가 차례로 이렇게 답하는 상황을 만든다."""
    return patch('accounts.payment_eligibility.report_payment_eligibility', side_effect=list(outcomes))


class MarkTests(TestCase):
    def test_identity_verification_queues_the_first_version(self):
        user = verified()

        row = row_of(user)
        self.assertEqual((row.version, row.delivered_version), (1, 0))

    def test_an_unverified_account_has_nothing_to_send(self):
        make_user()

        self.assertFalse(PaymentEligibility.objects.exists())

    def test_a_change_raises_the_version_and_makes_it_due_now(self):
        user = verified()
        PaymentEligibility.objects.update(attempts=9, next_attempt_at=timezone.now() + timedelta(hours=1))

        mark_changed(user)

        row = row_of(user)
        self.assertEqual(row.version, 2)
        self.assertEqual(row.attempts, 0)
        self.assertLessEqual(row.next_attempt_at, timezone.now())


class DeliverTests(TestCase):
    def test_sends_the_state_and_remembers_the_version(self):
        user = verified()

        with billing_answers(APPLIED) as client:
            report = deliver_due_eligibility()

        client.assert_called_once_with(
            user_public_id=user.public_id, version=1, legal_adult_from=None, guardian_consent=False
        )
        self.assertEqual(report.sent, 1)
        self.assertEqual(row_of(user).delivered_version, 1)

    def test_a_minor_is_sent_with_the_day_of_adulthood_and_the_consent(self):
        user = verified(birth_date=MINOR_BIRTH_DATE)
        GuardianConsent.objects.create(
            minor=user,
            guardian_email='parent@example.com',
            status=GuardianConsentStatus.CONSENTED,
            link_nonce='n',
            requested_at=timezone.now(),
            window_started_at=timezone.now(),
        )

        with billing_answers(APPLIED) as client:
            deliver_due_eligibility()

        self.assertEqual(client.call_args.kwargs['legal_adult_from'], date(2029, 6, 1))
        self.assertIs(client.call_args.kwargs['guardian_consent'], True)

    def test_nothing_is_sent_once_delivered(self):
        verified()
        with billing_answers(APPLIED):
            deliver_due_eligibility()

        with billing_answers() as client:
            report = deliver_due_eligibility()

        self.assertEqual(report.handled, 0)
        client.assert_not_called()

    def test_a_change_during_sending_is_sent_again(self):
        # 보내는 동안 보호자가 동의했다. 보낸 것은 그 전의 상태다. 다음 바퀴에 새 버전이 나간다
        user = verified()

        def changed_meanwhile(**kwargs):
            mark_changed(user)
            return APPLIED

        with patch('accounts.payment_eligibility.report_payment_eligibility', side_effect=changed_meanwhile):
            deliver_due_eligibility(batch_size=1)
        with billing_answers(APPLIED) as client:
            deliver_due_eligibility()

        self.assertEqual(client.call_args.kwargs['version'], 2)
        self.assertEqual(row_of(user).delivered_version, 2)

    def test_the_delivered_version_never_goes_back(self):
        # 늦게 끝난 워커가 앞선 버전을 적어도 더 높은 기록을 지우지 않는다
        user = verified()
        row = row_of(user)
        PaymentEligibility.objects.update(version=5, delivered_version=5)

        _mark_delivered(row.pk, 3, timezone.now())

        self.assertEqual(row_of(user).delivered_version, 5)

    def test_a_claimed_row_waits_for_its_lease(self):
        # 워커가 차지하고 답을 기다리다 죽었다. 임대가 끝날 때까지는 다른 워커가 보내지 않는다
        verified()
        now = timezone.now()
        _claim_next(now)

        with at(now + LEASE - timedelta(seconds=1)), billing_answers() as client:
            early = deliver_due_eligibility()
        with at(now + LEASE), billing_answers(APPLIED):
            late = deliver_due_eligibility()

        client.assert_not_called()
        self.assertEqual((early.handled, late.sent), (0, 1))


class RetryTests(TestCase):
    def setUp(self):
        self.user = verified()
        self.start = timezone.now()

    def fail_at(self, moment):
        with (
            at(moment),
            billing_answers(BillingUnavailableError('결제 서버가 404 로 답했다')),
            self.assertLogs('accounts.payment_eligibility', level='WARNING') as logs,
        ):
            report = deliver_due_eligibility()
        return report, logs

    def test_failure_is_kept_and_tried_later(self):
        report, _ = self.fail_at(self.start)

        row = row_of(self.user)
        self.assertEqual(report.retried, 1)
        self.assertEqual(row.attempts, 1)
        self.assertEqual(row.delivered_version, 0)
        self.assertEqual(row.next_attempt_at, self.start + FIRST_RETRY_DELAY)
        self.assertIn('404', row.last_error)

    def test_it_succeeds_once_the_billing_server_answers(self):
        self.fail_at(self.start)

        with at(self.start + FIRST_RETRY_DELAY), billing_answers(APPLIED):
            report = deliver_due_eligibility()

        row = row_of(self.user)
        self.assertEqual(report.sent, 1)
        self.assertEqual((row.delivered_version, row.attempts, row.last_error), (1, 0, ''))

    def test_failure_is_logged_without_naming_the_user(self):
        _, logs = self.fail_at(self.start)

        record = logs.records[0]
        self.assertEqual(record.operation, 'payment_eligibility.deliver')
        self.assertEqual(record.error_code, 'billing.unavailable')
        logged = record.getMessage() + ' '.join(str(value) for value in vars(record).values())
        self.assertNotIn(str(self.user.public_id), logged)


@override_settings(BILLING_SECRET=SECRET)
class WorkerCommandTests(TestCase):
    def test_the_worker_sends_both_kinds(self):
        verified()

        with (
            patch('accounts.welcome_credit.grant_welcome_credit', return_value='granted'),
            billing_answers(APPLIED),
        ):
            output = StringIO()
            call_command('send_welcome_credits', '--once', stdout=output)

        self.assertIn('지급 1건', output.getvalue())
        self.assertIn('결제 자격 알림 1건', output.getvalue())
