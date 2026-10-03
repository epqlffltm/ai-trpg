# auth-server/accounts/tests/test_outbox.py

"""
메일 발송함을 검증한다. 적기, 보내기, 실패 후 재시도, 버리기.

다른 테스트는 메일을 그 자리에서 보내는 방식(inline)으로 돈다.
이 파일은 실제 운영과 같은 방식(outbox)으로 바꿔서 돈다.
"""

import smtplib
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.mail_crypto import decrypt_mail_body
from accounts.models import OutgoingMail, OutgoingMailStatus, User
from accounts.outbox import (
    FIRST_RETRY_DELAY,
    MAIL_SEND_DEADLINE,
    deliver_due_mail,
    enqueue_mail,
)
from accounts.tests.helpers import code_from

SIGNUP_URL = reverse('accounts:signup')
SIGNUP_VERIFY_URL = reverse('accounts:signup-verify')
RESET_URL = reverse('accounts:password-reset')

EMAIL = 'someone@example.com'
PASSWORD = 'correct-horse-battery'


def enqueue(**overrides) -> OutgoingMail:
    """발송함에 메일 한 통을 적고 그 행을 돌려준다."""
    fields = {'to_email': EMAIL, 'subject': '제목', 'body': '본문 123456'}
    fields.update(overrides)
    enqueue_mail(**fields)
    return OutgoingMail.objects.latest('id')


def at(moment):
    """발송함 쪽의 시계를 moment 로 맞춘다."""
    return patch('accounts.outbox.timezone.now', return_value=moment)


def failing_mail_server(error: Exception | None = None):
    """메일 서버가 죽어 있는 상황을 만든다."""
    return patch(
        'accounts.outbox.send_mail',
        side_effect=error or smtplib.SMTPServerDisconnected('Connection unexpectedly closed'),
    )


@override_settings(MAIL_DELIVERY='outbox')
class EnqueueTests(TestCase):
    def test_writes_a_row_and_sends_nothing(self):
        queued = enqueue()

        self.assertEqual(queued.status, OutgoingMailStatus.PENDING)
        self.assertEqual(queued.attempts, 0)
        self.assertEqual(queued.expires_at - queued.next_attempt_at, MAIL_SEND_DEADLINE)
        self.assertEqual(len(mail.outbox), 0)

    def test_body_is_not_stored_as_written(self):
        queued = enqueue(body='인증 코드 123456')

        # DB 를 읽을 수 있는 사람이 보내기 전의 코드를 얻지 못하게 한다
        self.assertNotIn('123456', queued.body)
        self.assertNotIn('인증 코드', queued.body)

    def test_same_body_is_stored_differently_each_time(self):
        first = enqueue(body='인증 코드 123456')
        second = enqueue(body='인증 코드 123456')

        # 같으면, 저장된 값끼리 비교해 "같은 코드가 나갔다" 를 알 수 있다
        self.assertNotEqual(first.body, second.body)

    def test_row_disappears_when_the_surrounding_transaction_fails(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                enqueue()
                # 메일을 적은 뒤에 같은 트랜잭션의 다른 일이 실패한다
                raise RuntimeError

        # 메일을 직접 보냈다면 이미 나가 버렸을 것이다. 적어 둔 것이라 함께 취소된다
        self.assertEqual(OutgoingMail.objects.count(), 0)

    @override_settings(MAIL_DELIVERY='inline')
    def test_inline_mode_sends_immediately_without_a_row(self):
        enqueue_mail(to_email=EMAIL, subject='제목', body='본문')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(OutgoingMail.objects.count(), 0)


@override_settings(MAIL_DELIVERY='outbox')
class DeliverTests(TestCase):
    def test_sends_and_deletes_the_row(self):
        enqueue()

        report = deliver_due_mail()

        self.assertEqual((report.sent, report.retried, report.discarded), (1, 0, 0))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertEqual(mail.outbox[0].body, '본문 123456')
        # 본문에 인증 코드가 들어 있다. 보낸 메일은 남기지 않는다
        self.assertEqual(OutgoingMail.objects.count(), 0)

    def test_mail_that_cannot_be_decrypted_is_discarded(self):
        queued = enqueue()
        # 암호화한 뒤에 비밀키가 바뀌었거나 DB 의 값을 누가 고친 경우
        OutgoingMail.objects.filter(pk=queued.pk).update(body='not-a-valid-ciphertext')

        with self.assertLogs('accounts.outbox', level='ERROR'):
            report = deliver_due_mail()

        queued.refresh_from_db()
        self.assertEqual(report.discarded, 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(queued.status, OutgoingMailStatus.DISCARDED)
        self.assertEqual(queued.body, '')
        self.assertIn('UnreadableMailBodyError', queued.last_error)

    @override_settings(SECRET_KEY='another-secret-key-for-this-test-only')
    def test_mail_encrypted_with_another_key_is_discarded(self):
        with override_settings(SECRET_KEY='the-key-used-when-the-mail-was-queued'):
            enqueue()

        with self.assertLogs('accounts.outbox', level='ERROR'):
            report = deliver_due_mail()

        self.assertEqual(report.discarded, 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_does_nothing_when_the_outbox_is_empty(self):
        report = deliver_due_mail()

        self.assertEqual(report.handled, 0)

    def test_sends_in_the_order_they_were_queued(self):
        for subject in ('첫째', '둘째', '셋째'):
            enqueue(subject=subject)

        deliver_due_mail()

        self.assertEqual([message.subject for message in mail.outbox], ['첫째', '둘째', '셋째'])

    def test_handles_at_most_one_batch(self):
        for _ in range(5):
            enqueue()

        report = deliver_due_mail(batch_size=2)

        self.assertEqual(report.sent, 2)
        self.assertEqual(OutgoingMail.objects.count(), 3)


@override_settings(MAIL_DELIVERY='outbox')
class RetryTests(TestCase):
    def setUp(self):
        self.start = timezone.now()
        with at(self.start):
            self.queued = enqueue()

    def fail_at(self, moment):
        with at(moment), failing_mail_server():
            return deliver_due_mail()

    def test_failure_keeps_the_mail_and_records_the_error(self):
        report = self.fail_at(self.start)

        self.queued.refresh_from_db()
        self.assertEqual(report.retried, 1)
        self.assertEqual(self.queued.status, OutgoingMailStatus.PENDING)
        self.assertEqual(self.queued.attempts, 1)
        self.assertIn('SMTPServerDisconnected', self.queued.last_error)
        # 다시 보내야 하므로 본문은 그대로 있다
        self.assertEqual(decrypt_mail_body(self.queued.body), '본문 123456')

    def test_failed_mail_waits_before_the_next_attempt(self):
        self.fail_at(self.start)

        with at(self.start + FIRST_RETRY_DELAY - timedelta(seconds=1)):
            too_early = deliver_due_mail()
        with at(self.start + FIRST_RETRY_DELAY):
            on_time = deliver_due_mail()

        self.assertEqual(too_early.handled, 0)
        self.assertEqual(on_time.sent, 1)

    def test_wait_doubles_after_each_failure(self):
        moment = self.start
        waits = []
        for _ in range(4):
            self.fail_at(moment)
            self.queued.refresh_from_db()
            waits.append(self.queued.next_attempt_at - moment)
            moment = self.queued.next_attempt_at

        self.assertEqual(waits, [FIRST_RETRY_DELAY * factor for factor in (1, 2, 4, 8)])

    def test_one_failing_mail_does_not_block_the_others(self):
        self.fail_at(self.start)
        with at(self.start + timedelta(seconds=1)):
            enqueue(subject='뒤에 온 메일')
            report = deliver_due_mail()

        # 실패한 메일은 기다리는 중이고, 뒤에 온 메일은 바로 나간다
        self.assertEqual(report.sent, 1)
        self.assertEqual(mail.outbox[0].subject, '뒤에 온 메일')

    def test_timeout_is_retried_like_any_other_failure(self):
        with at(self.start), failing_mail_server(TimeoutError('timed out')):
            report = deliver_due_mail()

        self.assertEqual(report.retried, 1)


@override_settings(MAIL_DELIVERY='outbox')
class DiscardTests(TestCase):
    def setUp(self):
        self.start = timezone.now()
        with at(self.start):
            self.queued = enqueue()

    def test_discards_mail_that_could_not_be_sent_in_time(self):
        with at(self.start), failing_mail_server():
            deliver_due_mail()

        with at(self.start + MAIL_SEND_DEADLINE), self.assertLogs('accounts.outbox', level='ERROR') as logs:
            report = deliver_due_mail()

        self.queued.refresh_from_db()
        self.assertEqual(report.discarded, 1)
        self.assertEqual(self.queued.status, OutgoingMailStatus.DISCARDED)
        self.assertEqual(self.queued.discarded_at, self.start + MAIL_SEND_DEADLINE)
        self.assertEqual(len(mail.outbox), 0)
        # 운영자가 볼 기록
        self.assertIn(f'id={self.queued.pk}', logs.output[0])
        self.assertIn('SMTPServerDisconnected', self.queued.last_error)

    def test_discarded_mail_keeps_no_body_and_no_address_in_the_log(self):
        with at(self.start + MAIL_SEND_DEADLINE), self.assertLogs('accounts.outbox', level='ERROR') as logs:
            deliver_due_mail()

        self.queued.refresh_from_db()
        # 본문에는 인증 코드가 있었다. 버릴 때 함께 지운다
        self.assertEqual(self.queued.body, '')
        self.assertNotIn(EMAIL, logs.output[0])
        self.assertNotIn('123456', logs.output[0])

    def test_late_mail_is_discarded_even_if_the_server_is_back(self):
        # 워커가 5분 넘게 멈춰 있다가 다시 뜬 경우. 늦은 인증 코드는 보내지 않는다
        with at(self.start + MAIL_SEND_DEADLINE + timedelta(minutes=10)), self.assertLogs('accounts.outbox', level='ERROR'):
            report = deliver_due_mail()

        self.assertEqual(report.discarded, 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_retry_is_never_scheduled_past_the_deadline(self):
        moment = self.start
        for _ in range(10):
            with at(moment), failing_mail_server():
                deliver_due_mail()
            self.queued.refresh_from_db()
            if self.queued.next_attempt_at >= self.queued.expires_at:
                break
            moment = self.queued.next_attempt_at

        # 미뤄진 시각이 버리는 시각을 넘지 않아야, 그 시각에 꺼내져 버려진다
        self.assertEqual(self.queued.next_attempt_at, self.queued.expires_at)

    def test_discarded_mail_is_not_picked_up_again(self):
        with at(self.start + MAIL_SEND_DEADLINE), self.assertLogs('accounts.outbox', level='ERROR'):
            deliver_due_mail()

        with at(self.start + MAIL_SEND_DEADLINE * 2):
            report = deliver_due_mail()

        self.assertEqual(report.handled, 0)


@override_settings(MAIL_DELIVERY='outbox')
class WorkerCommandTests(TestCase):
    def run_once(self) -> str:
        output = StringIO()
        call_command('send_outgoing_mail', '--once', stdout=output)
        return output.getvalue()

    def test_once_sends_what_is_due_and_reports(self):
        enqueue()
        enqueue()

        output = self.run_once()

        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('보냄 2건', output)

    def test_once_prints_nothing_when_there_is_nothing_to_do(self):
        self.assertEqual(self.run_once(), '')


@override_settings(MAIL_DELIVERY='outbox')
class RequestsDoNotSendMailTests(APITestCase):
    """요청을 처리하는 동안에는 메일 서버에 가지 않는다. 적기만 한다."""

    def signup(self, **overrides):
        payload = {'username': 'player_01', 'email': EMAIL, 'nickname': '플레이어', 'password': PASSWORD}
        payload.update(overrides)
        return self.client.post(SIGNUP_URL, payload, format='json')

    def test_signup_queues_the_code_mail(self):
        response = self.signup()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(OutgoingMail.objects.get().to_email, EMAIL)

    def test_queued_code_works_after_the_worker_sends_it(self):
        self.signup()

        deliver_due_mail()
        response = self.client.post(
            SIGNUP_VERIFY_URL,
            {'email': EMAIL, 'code': code_from(mail.outbox[0])},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_signup_succeeds_while_the_mail_server_is_down(self):
        with failing_mail_server():
            response = self.signup()

        # 메일 서버의 상태가 요청의 성공과 실패를 바꾸지 않는다
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(User.objects.filter(username='player_01').exists())

    def test_nothing_is_queued_when_signup_is_rejected(self):
        self.signup()
        OutgoingMail.objects.all().delete()

        response = self.signup(email='another@example.com')

        # 아이디가 겹쳐 거부됐다. 계정도 보낼 메일도 생기지 않는다
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(OutgoingMail.objects.count(), 0)

    def test_reset_request_never_talks_to_the_mail_server(self):
        User.objects.create_user(
            username='player_01', email=EMAIL, nickname='플레이어',
            password=PASSWORD, email_verified_at=timezone.now(),
        )

        with patch('accounts.outbox.send_mail') as mail_server:
            known = self.client.post(RESET_URL, {'email': EMAIL}, format='json')
            unknown = self.client.post(RESET_URL, {'email': 'nobody@example.com'}, format='json')

        # 가입된 주소든 아니든 요청 안에서는 메일 서버를 기다리지 않는다.
        # 기다리면 그 시간이 응답 시간에 드러나 가입 여부를 알려 준다
        mail_server.assert_not_called()
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(OutgoingMail.objects.count(), 1)
