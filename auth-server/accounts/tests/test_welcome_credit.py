# auth-server/accounts/tests/test_welcome_credit.py

"""
환영 크레딧을 검증한다. 메일함마다 한 번만 적기, 가입 인증과 함께 적기, 결제 서버에 맡기기, 실패 후 재시도.

결제 서버를 부르는 함수는 대부분 가짜로 바꿔 끼운다. 이 파일이 보는 것은 "언제 부르고 결과를 어떻게 적는가"다.
요청의 모양은 test_billing_client.py 가 본다. 끝에서 한 번, 가짜를 끼우지 않고 끝까지 지난다.
"""

import hashlib
import threading
import time
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.billing_client import ALREADY_GRANTED, DISABLED, GRANTED, BillingUnavailableError
from accounts.models import User, WelcomeCredit, WelcomeCreditStatus
from accounts.tests.billing_stub import SECRET, BillingStub
from accounts.tests.helpers import code_from, wrong_code_for
from accounts.welcome_credit import (
    DEFAULT_BATCH_SIZE,
    FIRST_RETRY_DELAY,
    MAX_RETRY_DELAY,
    deliver_due_welcome_credits,
    mailbox_key,
    mailbox_of,
    request_welcome_credit,
    request_welcome_credits_for_verified_users,
)

SIGNUP_URL = reverse('accounts:signup')
VERIFY_URL = reverse('accounts:signup-verify')

EMAIL = 'someone@example.com'
PASSWORD = 'correct-horse-battery'


def make_user(number: int = 1, email: str | None = None, verified: bool = True) -> User:
    """계정 하나를 만든다. number 로 아이디와 닉네임이 겹치지 않게 한다."""
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=email or f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password=PASSWORD,
        email_verified_at=timezone.now() if verified else None,
    )


def pending(number: int = 1, **overrides) -> WelcomeCredit:
    """맡기기 전인 줄 하나를 만든다."""
    fields = {
        'mailbox_key': mailbox_key(f'player{number}@example.com'),
        'user_public_id': uuid.uuid4(),
        'next_attempt_at': timezone.now(),
    }
    fields.update(overrides)
    return WelcomeCredit.objects.create(**fields)


def at(moment):
    """환영 크레딧 쪽의 시계를 moment 로 맞춘다."""
    return patch('accounts.welcome_credit.timezone.now', return_value=moment)


def billing_answers(*outcomes):
    """결제 서버가 차례로 이렇게 답하는 상황을 만든다. 예외를 넣으면 그 차례에 그 예외가 난다."""
    return patch('accounts.welcome_credit.grant_welcome_credit', side_effect=list(outcomes))


def billing_is_down():
    """결제 서버가 죽어 있는 상황을 만든다."""
    return patch(
        'accounts.welcome_credit.grant_welcome_credit',
        side_effect=BillingUnavailableError('결제 서버에 닿지 못했다: ConnectionRefusedError'),
    )


class MailboxTests(SimpleTestCase):
    def test_same_mailbox_whatever_the_case_or_the_tag(self):
        same = ['someone@example.com', 'Someone@Example.COM', 'someone+trpg@example.com', ' someone+a+b@example.com ']
        for email in same:
            with self.subTest(email):
                self.assertEqual(mailbox_of(email), 'someone@example.com')

    def test_different_mailboxes_stay_different(self):
        others = [
            'someone@example.org',
            'some.one@example.com',
            'someone2@example.com',
            'someone@mail.example.com',
        ]
        for email in others:
            with self.subTest(email):
                self.assertNotEqual(mailbox_of(email), 'someone@example.com')

    def test_only_the_tag_before_the_at_sign_is_cut(self):
        # 꼬리표는 사용자 이름에만 있다. @ 뒤는 건드리지 않는다
        self.assertEqual(mailbox_of('someone+tag@sub+domain.example.com'), 'someone@sub+domain.example.com')
        self.assertEqual(mailbox_of('+only-a-tag@example.com'), '@example.com')

    def test_key_is_the_same_for_the_same_mailbox(self):
        self.assertEqual(mailbox_key('someone@example.com'), mailbox_key('SomeOne+again@example.com'))
        self.assertNotEqual(mailbox_key('someone@example.com'), mailbox_key('someone@example.org'))
        self.assertRegex(mailbox_key('someone@example.com'), r'^[0-9a-f]{64}$')

    def test_key_cannot_be_rebuilt_from_the_address_alone(self):
        # 주소는 짐작할 수 있는 값이다. 그냥 해시면 DB 를 읽은 사람이 주소를 넣어 보며 가입 여부를 알아낸다
        plain = hashlib.sha256(b'someone@example.com').hexdigest()

        self.assertNotEqual(mailbox_key('someone@example.com'), plain)
        with override_settings(SECRET_KEY='another-secret-key-for-this-test-only'):
            other = mailbox_key('someone@example.com')
        self.assertNotEqual(mailbox_key('someone@example.com'), other)


class RequestTests(TestCase):
    def test_writes_one_pending_row_for_the_user(self):
        user = make_user()

        created = request_welcome_credit(user)

        claim = WelcomeCredit.objects.get()
        self.assertTrue(created)
        self.assertEqual(claim.user_public_id, user.public_id)
        self.assertEqual(claim.status, WelcomeCreditStatus.PENDING)
        self.assertEqual(claim.attempts, 0)
        self.assertLessEqual(claim.next_attempt_at, timezone.now())
        self.assertIsNone(claim.finished_at)

    def test_does_not_store_the_address(self):
        user = make_user(email='someone@example.com')

        request_welcome_credit(user)

        row = WelcomeCredit.objects.values().get()
        self.assertNotIn('someone', ' '.join(str(value) for value in row.values()))

    def test_asking_twice_writes_once(self):
        user = make_user()

        request_welcome_credit(user)
        created = request_welcome_credit(user)

        self.assertFalse(created)
        self.assertEqual(WelcomeCredit.objects.count(), 1)

    def test_another_account_on_the_same_mailbox_gets_nothing(self):
        first = make_user(1, email='someone@example.com')
        second = make_user(2, email='someone+second@example.com')
        request_welcome_credit(first)

        created = request_welcome_credit(second)

        self.assertFalse(created)
        # 먼저 온 계정의 줄이 그대로다. 나중 계정으로 바뀌지 않는다
        self.assertEqual(WelcomeCredit.objects.get().user_public_id, first.public_id)

    def test_finished_row_still_blocks_the_mailbox(self):
        first = make_user(1, email='someone@example.com')
        request_welcome_credit(first)
        WelcomeCredit.objects.update(status=WelcomeCreditStatus.GRANTED, finished_at=timezone.now())
        first.delete()
        again = make_user(2, email='someone@example.com')

        created = request_welcome_credit(again)

        self.assertFalse(created)
        self.assertEqual(WelcomeCredit.objects.get().status, WelcomeCreditStatus.GRANTED)

    def test_different_mailboxes_each_get_a_row(self):
        request_welcome_credit(make_user(1))
        request_welcome_credit(make_user(2))

        self.assertEqual(WelcomeCredit.objects.count(), 2)

    def test_row_disappears_when_the_surrounding_transaction_fails(self):
        user = make_user()

        with self.assertRaises(RuntimeError), transaction.atomic():
            request_welcome_credit(user)
            raise RuntimeError('가입 인증이 중간에 실패했다')

        self.assertEqual(WelcomeCredit.objects.count(), 0)


class SignupTests(APITestCase):
    """가입 인증을 실제 주소로 지난다. 인증과 함께 줄이 적히는지 본다."""

    def signup(self, number: int = 1, email: str = EMAIL):
        payload = {'username': f'player_{number:02d}', 'email': email, 'nickname': f'플레이어{number}', 'password': PASSWORD}
        return self.client.post(SIGNUP_URL, payload, format='json')

    def verify(self, email: str = EMAIL, code: str | None = None):
        return self.client.post(VERIFY_URL, {'email': email, 'code': code or code_from(mail.outbox[-1])}, format='json')

    def signup_and_verify(self, number: int = 1, email: str = EMAIL) -> User:
        self.signup(number, email)
        response = self.verify(email)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return User.objects.get(username=f'player_{number:02d}')

    def test_verifying_the_email_queues_the_welcome_credit(self):
        user = self.signup_and_verify()

        claim = WelcomeCredit.objects.get()
        self.assertEqual(claim.user_public_id, user.public_id)
        self.assertEqual(claim.status, WelcomeCreditStatus.PENDING)

    def test_verifying_never_talks_to_the_billing_server(self):
        # 결제 서버가 죽어 있어도 가입은 끝난다. 요청을 처리하는 쪽은 적기만 한다
        with patch('accounts.billing_client.grant_welcome_credit') as client, billing_is_down() as worker_client:
            response_user = self.signup_and_verify()

        self.assertTrue(response_user.is_email_verified)
        client.assert_not_called()
        worker_client.assert_not_called()

    def test_signing_up_without_verifying_queues_nothing(self):
        # 인증하지 않은 계정은 주소의 주인인지 모른다. 남의 주소로 가입만 해서 크레딧을 받을 수 없다
        self.signup()

        self.assertEqual(WelcomeCredit.objects.count(), 0)

    def test_wrong_code_queues_nothing(self):
        self.signup()

        response = self.verify(code=wrong_code_for(code_from(mail.outbox[-1])))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WelcomeCredit.objects.count(), 0)

    def test_deleting_the_account_and_signing_up_again_does_not_queue_twice(self):
        first = self.signup_and_verify(1)
        first_public_id = first.public_id
        first.delete()

        again = self.signup_and_verify(2)

        # 가입은 된다. 받는 것만 한 번이다
        self.assertTrue(again.is_email_verified)
        self.assertNotEqual(again.public_id, first_public_id)
        self.assertEqual(WelcomeCredit.objects.get().user_public_id, first_public_id)

    def test_tagged_addresses_of_one_mailbox_queue_once(self):
        first = self.signup_and_verify(1, 'someone+one@example.com')
        second = self.signup_and_verify(2, 'someone+two@example.com')

        self.assertTrue(second.is_email_verified)
        self.assertEqual(WelcomeCredit.objects.get().user_public_id, first.public_id)

    def test_verification_is_undone_when_the_row_cannot_be_written(self):
        # 둘은 한 트랜잭션이다. 줄을 못 적었으면 인증도 안 된 것이고, 같은 코드로 다시 할 수 있다
        self.signup()
        code = code_from(mail.outbox[-1])

        with patch('accounts.services.request_welcome_credit', side_effect=RuntimeError('DB 가 끊겼다')):
            with self.assertRaises(RuntimeError):
                self.verify(code=code)

        self.assertFalse(User.objects.get(username='player_01').is_email_verified)
        self.assertEqual(self.verify(code=code).status_code, status.HTTP_200_OK)
        self.assertEqual(WelcomeCredit.objects.count(), 1)


class DeliverTests(TestCase):
    def test_marks_the_row_with_what_the_billing_server_answered(self):
        outcomes = {
            GRANTED: WelcomeCreditStatus.GRANTED,
            ALREADY_GRANTED: WelcomeCreditStatus.ALREADY_GRANTED,
            DISABLED: WelcomeCreditStatus.DISABLED,
        }
        for number, (outcome, expected_status) in enumerate(outcomes.items(), start=1):
            with self.subTest(outcome):
                claim = pending(number)
                with billing_answers(outcome):
                    report = deliver_due_welcome_credits()

                claim.refresh_from_db()
                self.assertEqual(claim.status, expected_status)
                self.assertIsNotNone(claim.finished_at)
                self.assertEqual(report.granted, 1 if outcome == GRANTED else 0)
                self.assertEqual(report.skipped, 0 if outcome == GRANTED else 1)

    def test_asks_for_the_user_written_on_the_row(self):
        claim = pending()

        with billing_answers(GRANTED) as client:
            deliver_due_welcome_credits()

        client.assert_called_once_with(user_public_id=claim.user_public_id)

    def test_does_nothing_when_nothing_is_due(self):
        with billing_answers() as client:
            report = deliver_due_welcome_credits()

        self.assertEqual(report.handled, 0)
        client.assert_not_called()

    def test_finished_rows_are_not_delivered_again(self):
        pending()
        with billing_answers(GRANTED):
            deliver_due_welcome_credits()

        with billing_answers() as client:
            report = deliver_due_welcome_credits()

        self.assertEqual(report.handled, 0)
        client.assert_not_called()

    def test_rows_that_are_not_due_yet_wait(self):
        pending(next_attempt_at=timezone.now() + timedelta(minutes=1))

        with billing_answers() as client:
            report = deliver_due_welcome_credits()

        self.assertEqual(report.handled, 0)
        client.assert_not_called()

    def test_delivers_in_the_order_they_became_due(self):
        now = timezone.now()
        later = pending(1, next_attempt_at=now - timedelta(seconds=1))
        earlier = pending(2, next_attempt_at=now - timedelta(seconds=9))

        with billing_answers(GRANTED, GRANTED) as client:
            deliver_due_welcome_credits()

        asked = [call.kwargs['user_public_id'] for call in client.call_args_list]
        self.assertEqual(asked, [earlier.user_public_id, later.user_public_id])

    def test_handles_at_most_one_batch(self):
        for number in range(DEFAULT_BATCH_SIZE + 3):
            pending(number)

        with patch('accounts.welcome_credit.grant_welcome_credit', return_value=GRANTED):
            report = deliver_due_welcome_credits()

        self.assertEqual(report.granted, DEFAULT_BATCH_SIZE)
        self.assertEqual(WelcomeCredit.objects.filter(status=WelcomeCreditStatus.PENDING).count(), 3)


class RetryTests(TestCase):
    def setUp(self):
        self.start = timezone.now()
        self.claim = pending(next_attempt_at=self.start)

    def fail_at(self, moment):
        """moment 에 워커가 돌았고 결제 서버가 죽어 있었다."""
        with at(moment), billing_is_down(), self.assertLogs('accounts.welcome_credit', level='WARNING') as logs:
            report = deliver_due_welcome_credits()
        self.claim.refresh_from_db()
        return report, logs

    def test_failure_keeps_the_row_pending_and_records_the_error(self):
        report, _ = self.fail_at(self.start)

        self.assertEqual(report.retried, 1)
        self.assertEqual(self.claim.status, WelcomeCreditStatus.PENDING)
        self.assertEqual(self.claim.attempts, 1)
        self.assertIn('ConnectionRefusedError', self.claim.last_error)
        self.assertIsNone(self.claim.finished_at)

    def test_failed_row_waits_before_the_next_attempt(self):
        self.fail_at(self.start)

        self.assertEqual(self.claim.next_attempt_at, self.start + FIRST_RETRY_DELAY)
        with at(self.start + FIRST_RETRY_DELAY - timedelta(seconds=1)), billing_answers() as client:
            report = deliver_due_welcome_credits()
        self.assertEqual(report.handled, 0)
        client.assert_not_called()

    def test_wait_doubles_after_each_failure(self):
        moment = self.start
        waits = []
        for _ in range(4):
            self.fail_at(moment)
            waits.append(self.claim.next_attempt_at - moment)
            moment = self.claim.next_attempt_at

        self.assertEqual(waits, [FIRST_RETRY_DELAY * factor for factor in (1, 2, 4, 8)])

    def test_wait_stops_growing_at_the_maximum(self):
        # 결제 서버가 오래 죽어 있었다. 간격이 끝없이 늘면 살아난 뒤에도 며칠을 기다린다
        for attempts in (10, 11, 40, 5000):
            with self.subTest(attempts):
                WelcomeCredit.objects.update(attempts=attempts, next_attempt_at=self.start)
                self.fail_at(self.start)
                self.assertEqual(self.claim.next_attempt_at, self.start + MAX_RETRY_DELAY)

    def test_never_gives_up(self):
        # 메일과 달리 버리지 않는다. 늦게 줘도 쓸모가 있다
        WelcomeCredit.objects.update(attempts=5000)

        self.fail_at(self.start + timedelta(days=30))

        self.assertEqual(self.claim.status, WelcomeCreditStatus.PENDING)

    def test_succeeds_once_the_billing_server_is_back(self):
        self.fail_at(self.start)

        with at(self.start + FIRST_RETRY_DELAY), billing_answers(GRANTED):
            report = deliver_due_welcome_credits()

        self.claim.refresh_from_db()
        self.assertEqual(report.granted, 1)
        self.assertEqual(self.claim.status, WelcomeCreditStatus.GRANTED)
        self.assertEqual(self.claim.finished_at, self.start + FIRST_RETRY_DELAY)
        self.assertEqual(self.claim.last_error, '')

    def test_one_failing_row_does_not_block_the_others(self):
        other = pending(2, next_attempt_at=self.start + timedelta(seconds=1))
        failure = BillingUnavailableError('결제 서버가 500 로 답했다')

        with at(self.start + timedelta(seconds=2)), billing_answers(failure, GRANTED):
            with self.assertLogs('accounts.welcome_credit', level='WARNING'):
                report = deliver_due_welcome_credits()

        other.refresh_from_db()
        self.assertEqual((report.retried, report.granted), (1, 1))
        self.assertEqual(other.status, WelcomeCreditStatus.GRANTED)

    def test_long_errors_are_cut_to_fit(self):
        with at(self.start), self.assertLogs('accounts.welcome_credit', level='WARNING'):
            with billing_answers(BillingUnavailableError('x' * 1000)):
                deliver_due_welcome_credits()

        self.claim.refresh_from_db()
        self.assertEqual(len(self.claim.last_error), 200)

    def test_failure_is_logged_without_naming_the_user(self):
        _, logs = self.fail_at(self.start)

        record = logs.records[0]
        self.assertEqual(record.operation, 'welcome_credit.deliver')
        self.assertEqual(record.error_code, 'billing.unavailable')
        self.assertEqual(record.welcome_credit_id, self.claim.pk)
        logged = record.getMessage() + ' '.join(str(value) for value in vars(record).values())
        self.assertNotIn(str(self.claim.user_public_id), logged)
        self.assertNotIn(self.claim.mailbox_key, logged)


class TwoWorkersTests(TransactionTestCase):
    """워커 둘이 함께 돈다. 진짜 트랜잭션 둘이 있어야 해서, 테스트를 트랜잭션으로 감싸지 않는 종류를 쓴다."""

    def test_a_row_being_delivered_is_skipped_by_the_other_worker(self):
        busy = pending(1)
        free = pending(2, next_attempt_at=timezone.now() + timedelta(milliseconds=1))
        calling = threading.Event()
        finish = threading.Event()
        asked_by_first = []

        def slow_billing(*, user_public_id):
            # 첫 워커가 결제 서버를 부르는 중이다. 줄을 잠근 채로 답을 기다린다
            asked_by_first.append(user_public_id)
            calling.set()
            finish.wait(timeout=10)
            return GRANTED

        def first_worker():
            try:
                with patch('accounts.welcome_credit.grant_welcome_credit', side_effect=slow_billing):
                    deliver_due_welcome_credits(batch_size=1)
            finally:
                connection.close()

        thread = threading.Thread(target=first_worker)
        thread.start()
        try:
            self.assertTrue(calling.wait(timeout=10))
            started = time.monotonic()
            with at(timezone.now() + timedelta(seconds=1)), billing_answers(GRANTED) as second_client:
                report = deliver_due_welcome_credits(batch_size=5)
            waited = time.monotonic() - started
        finally:
            finish.set()
            thread.join(timeout=10)

        # 둘째 워커는 잠긴 줄을 기다리지 않고 건너뛰어, 다른 줄만 맡겼다.
        # 기다렸다면 첫 워커가 끝날 때(10초 뒤)까지 여기서 멈춰 있었을 것이다
        self.assertLess(waited, 5)
        self.assertEqual(asked_by_first, [busy.user_public_id])
        second_client.assert_called_once_with(user_public_id=free.user_public_id)
        self.assertEqual(report.granted, 1)
        self.assertEqual(WelcomeCredit.objects.filter(status=WelcomeCreditStatus.GRANTED).count(), 2)

    def test_a_worker_that_dies_mid_call_leaves_the_row_pending(self):
        claim = pending()

        with patch('accounts.welcome_credit.grant_welcome_credit', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                deliver_due_welcome_credits()

        claim.refresh_from_db()
        self.assertEqual(claim.status, WelcomeCreditStatus.PENDING)
        self.assertEqual(claim.attempts, 0)


@override_settings(BILLING_SECRET=SECRET)
class WorkerCommandTests(TestCase):
    def run_once(self) -> str:
        output = StringIO()
        call_command('send_welcome_credits', '--once', stdout=output)
        return output.getvalue()

    def test_once_delivers_what_is_due_and_reports(self):
        pending(1)
        pending(2)
        pending(3)

        with billing_answers(GRANTED, ALREADY_GRANTED, BillingUnavailableError('결제 서버가 503 로 답했다')):
            with self.assertLogs('accounts.welcome_credit', level='WARNING'):
                output = self.run_once()

        self.assertIn('지급 1건, 주지 않음 1건, 다시 시도 예정 1건', output)

    def test_once_prints_nothing_when_there_is_nothing_to_do(self):
        self.assertEqual(self.run_once(), '')

    @override_settings(BILLING_SECRET='')
    def test_refuses_to_run_without_the_secret(self):
        claim = pending()

        with billing_answers() as client, self.assertRaisesMessage(CommandError, 'BILLING_SECRET'):
            self.run_once()

        # 줄마다 실패를 쌓지 않는다. 설정을 고친 뒤 바로 나갈 수 있게 그대로 둔다
        claim.refresh_from_db()
        client.assert_not_called()
        self.assertEqual(claim.attempts, 0)


class ExistingAccountsTests(TestCase):
    def run_command(self) -> str:
        output = StringIO()
        call_command('request_welcome_credits', stdout=output)
        return output.getvalue()

    def test_queues_every_verified_account_once(self):
        first = make_user(1)
        second = make_user(2)
        make_user(3, verified=False)

        output = self.run_command()

        queued = set(WelcomeCredit.objects.values_list('user_public_id', flat=True))
        self.assertEqual(queued, {first.public_id, second.public_id})
        self.assertIn('2개', output)

    def test_running_again_queues_nothing_new(self):
        make_user(1)
        self.run_command()

        output = self.run_command()

        self.assertEqual(WelcomeCredit.objects.count(), 1)
        self.assertIn('0개', output)

    def test_the_account_verified_first_gets_the_shared_mailbox(self):
        now = timezone.now()
        late = make_user(1, email='someone+late@example.com')
        early = make_user(2, email='someone+early@example.com')
        User.objects.filter(pk=late.pk).update(email_verified_at=now)
        User.objects.filter(pk=early.pk).update(email_verified_at=now - timedelta(days=3))

        created = request_welcome_credits_for_verified_users()

        self.assertEqual(created, 1)
        self.assertEqual(WelcomeCredit.objects.get().user_public_id, early.public_id)


class EndToEndTests(APITestCase):
    """가짜를 끼우지 않는다. 가입 인증부터 결제 서버가 받는 요청까지 지난다."""

    def test_signup_ends_with_a_signed_request_for_that_user(self):
        payload = {'username': 'player_01', 'email': EMAIL, 'nickname': '플레이어', 'password': PASSWORD}
        self.client.post(SIGNUP_URL, payload, format='json')
        self.client.post(VERIFY_URL, {'email': EMAIL, 'code': code_from(mail.outbox[-1])}, format='json')
        user = User.objects.get(username='player_01')

        with BillingStub() as stub, override_settings(BILLING_URL=stub.url, BILLING_SECRET=SECRET):
            output = StringIO()
            call_command('send_welcome_credits', '--once', stdout=output)
            # 다시 돌려도 또 부르지 않는다
            call_command('send_welcome_credits', '--once', stdout=StringIO())

        self.assertEqual(len(stub.requests), 1)
        request = stub.requests[0]
        self.assertTrue(request.has_valid_signature())
        self.assertIn(str(user.public_id).encode(), request.body)
        # 메일 주소는 결제 서버에 보내지 않는다
        self.assertNotIn(b'someone', request.body)
        self.assertEqual(WelcomeCredit.objects.get().status, WelcomeCreditStatus.GRANTED)
        self.assertIn('지급 1건', output.getvalue())

    def test_a_dead_billing_server_only_delays_the_credit(self):
        claim = pending()

        with BillingStub(status_code=503, body=b'') as stub:
            with override_settings(BILLING_URL=stub.url, BILLING_SECRET=SECRET):
                with self.assertLogs('accounts.welcome_credit', level='WARNING'):
                    first = deliver_due_welcome_credits()
                stub.status_code = 201
                stub.body = b'{"status":"granted","granted":"1000","expires_at":"2026-03-09T09:00:00Z"}'
                with at(timezone.now() + FIRST_RETRY_DELAY):
                    second = deliver_due_welcome_credits()

        claim.refresh_from_db()
        self.assertEqual((first.retried, second.granted), (1, 1))
        self.assertEqual(claim.status, WelcomeCreditStatus.GRANTED)
        self.assertEqual(len(stub.requests), 2)
