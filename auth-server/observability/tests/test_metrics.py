# auth-server/observability/tests/test_metrics.py

"""
메트릭을 세는 곳을 검증한다. 이름, 단위, label 이 docs/observability.md 의 "메트릭"의 표와 같은지 본다.
메모리에 모으는 것(observability/tests/metrics.py)으로 읽는다.
끝에서 끝까지(Prometheus 에 들어오는가)는 CI 의 stack 이 본다.

  - HTTP 셋(observability/request_metrics.py)과 db_up(config/health.py)
  - 작업 넷(observability/jobs.py 의 run_as_job)과 발송함에 남은 메일(send_outgoing_mail)
  - 보낸 메일(accounts/outbox.py)
  - 밀린 탈퇴와 알리지 못한 탈퇴 알림(send_welcome_credits 가 바퀴마다 적는다)
  - 시도 횟수 제한(accounts/attempt_limits.py)
"""

import runpy
import smtplib
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import redis
from django.core.management import call_command
from django.db import DatabaseError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts import withdrawal
from accounts.attempt_limits import AttemptLimit, TooManyAttemptsError, count_attempt, count_failure, ensure_not_blocked
from accounts.mail import send_signup_code
from accounts.models import MailKind, OutgoingMail, User, WithdrawalNotice
from accounts.outbox import MAIL_SEND_DEADLINE, deliver_due_mail, enqueue_mail
from accounts.tests.billing_stub import SECRET
from accounts.tests.helpers import delete_attempt_keys, reset_redis_breaker
from accounts.withdrawal_client import WithdrawalUndeliveredError
from accounts.withdrawal_schedule import GRACE
from observability.jobs import run_as_job
from observability.metrics import DURATION_BUCKETS, OTHER_METHOD, method_label, record_request
from observability.request_metrics import RequestMetricsMiddleware
from observability.tests.metrics import record_metrics

JWKS = '/api/v1/auth/jwks'
EMAIL = 'someone@example.com'
LIMIT = AttemptLimit(name='test-limit', max_attempts=1, window=timedelta(minutes=10))
GUNICORN_CONFIG = Path(__file__).resolve().parents[2] / 'gunicorn.conf.py'


class RequestTests(TestCase):
    def setUp(self) -> None:
        self.metrics = record_metrics(self)

    def test_a_request_is_counted_by_method_route_and_status(self):
        self.client.get(JWKS)

        labels = {'method': 'GET', 'route': JWKS}
        self.assertEqual(self.metrics.value('http_server_requests', **labels, status_code=200), 1)
        self.assertEqual(self.metrics.value('http_server_request_duration', **labels), 1)
        # 끝난 요청은 처리 중인 수에서 빠진다
        self.assertEqual(self.metrics.value('http_server_active_requests'), 0)

    def test_the_route_is_the_template_and_unmatched_is_one_label(self):
        self.client.post('/api/v1/auth/login', {}, content_type='application/json')
        self.client.get('/no/such/secret-path')

        routes = {point.labels['route'] for point in self.metrics.points('http_server_requests')}
        self.assertEqual(routes, {'/api/v1/auth/login', '(unmatched)'})

    def test_the_duration_is_in_seconds_with_the_shared_buckets(self):
        self.client.get('/health')

        (point,) = self.metrics.points('http_server_request_duration')
        self.assertEqual(point.unit, 's')
        self.assertEqual(self.metrics.bounds('http_server_request_duration'), DURATION_BUCKETS)

    def test_readiness_records_the_database_state(self):
        self.client.get('/health/ready')
        self.assertEqual(self.metrics.value('db_up'), 1)

        with patch('config.health.ping_database', side_effect=DatabaseError('닿지 않는다')):
            response = self.client.get('/health/ready')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.metrics.value('db_up'), 0)


class MiddlewareTests(SimpleTestCase):
    def setUp(self) -> None:
        self.metrics = record_metrics(self)

    def test_a_request_that_raises_is_counted_as_500(self):
        def broken(request) -> HttpResponse:
            raise RuntimeError('부서졌다')

        with self.assertRaises(RuntimeError):
            RequestMetricsMiddleware(broken)(RequestFactory().get('/x'))

        self.assertEqual(self.metrics.value('http_server_requests', status_code=500), 1)
        self.assertEqual(self.metrics.value('http_server_active_requests'), 0)

    def test_an_unknown_method_is_one_label(self):
        self.assertEqual(method_label('GET'), 'GET')
        self.assertEqual(method_label('BREW'), OTHER_METHOD)

    def test_gunicorn_loads_the_app_after_forking(self):
        # 갈라지기 전에 불러오면 보내는 스레드가 워커에 따라오지 않는다(observability/metrics.py)
        self.assertIs(runpy.run_path(str(GUNICORN_CONFIG))['preload_app'], False)


class NoProviderTests(SimpleTestCase):
    def test_recording_without_a_provider_does_nothing(self):
        # 끼운 것이 없으면(NoOp) 세어도 아무 일이 없다. 테스트가 아닌 PC 에서 띄운 서버와 같다
        record_request('GET', '/health', 200, 0.01)


class JobTests(SimpleTestCase):
    def setUp(self) -> None:
        self.metrics = record_metrics(self)

    def test_a_job_is_counted(self):
        with run_as_job('account.delete_unverified'):
            self.assertEqual(self.metrics.value('background_jobs_running', operation='account.delete_unverified'), 1)

        labels = {'operation': 'account.delete_unverified'}
        self.assertEqual(self.metrics.value('background_jobs_started', **labels), 1)
        self.assertEqual(self.metrics.value('background_jobs_finished', **labels, result='success'), 1)
        self.assertEqual(self.metrics.value('background_jobs_running', **labels), 0)
        self.assertEqual(self.metrics.value('background_job_duration', **labels), 1)

    def test_a_failed_job_is_a_server_error(self):
        with self.assertRaises(RuntimeError), run_as_job('security.send_digest'):
            raise RuntimeError('부서졌다')

        self.assertEqual(
            self.metrics.value('background_jobs_finished', operation='security.send_digest', result='server_error'), 1
        )

    def test_a_job_stopped_by_hand_is_cancelled(self):
        with self.assertRaises(KeyboardInterrupt), run_as_job('mail.deliver_outgoing'):
            raise KeyboardInterrupt

        self.assertEqual(
            self.metrics.value('background_jobs_finished', operation='mail.deliver_outgoing', result='cancelled'), 1
        )


def failing_mail_server():
    """메일 서버가 죽어 있는 상황을 만든다."""
    return patch('accounts.outbox.send_mail', side_effect=smtplib.SMTPServerDisconnected('끊겼다'))


@override_settings(MAIL_DELIVERY='outbox')
class MailTests(TestCase):
    def setUp(self) -> None:
        self.metrics = record_metrics(self)

    def test_the_kind_is_written_with_the_mail(self):
        send_signup_code(email=EMAIL, code='123456')

        self.assertEqual(OutgoingMail.objects.get().kind, MailKind.SIGNUP_CODE)

    def test_a_sent_mail_is_counted_by_its_kind(self):
        enqueue_mail(to_email=EMAIL, subject='제목', body='본문', kind=MailKind.PASSWORD_RESET)

        deliver_due_mail()

        self.assertEqual(self.metrics.value('emails_sent', kind='password_reset', result='sent'), 1)

    def test_a_failed_try_is_counted_as_retried(self):
        enqueue_mail(to_email=EMAIL, subject='제목', body='본문', kind=MailKind.LOGIN_CODE)

        with failing_mail_server():
            deliver_due_mail()

        self.assertEqual(self.metrics.value('emails_sent', kind='login_code', result='retried'), 1)
        self.assertIsNone(self.metrics.value('emails_sent', kind='login_code', result='sent'))

    def test_a_mail_past_its_deadline_is_counted_as_discarded(self):
        enqueue_mail(to_email=EMAIL, subject='제목', body='본문', kind=MailKind.SECURITY_DIGEST)

        later = timezone.now() + MAIL_SEND_DEADLINE + timedelta(seconds=1)
        with patch('accounts.outbox.timezone.now', return_value=later):
            deliver_due_mail()

        self.assertEqual(self.metrics.value('emails_sent', kind='security_digest', result='discarded'), 1)

    def test_a_mail_without_a_kind_is_other(self):
        enqueue_mail(to_email=EMAIL, subject='제목', body='본문')

        deliver_due_mail()

        self.assertEqual(self.metrics.value('emails_sent', kind='other', result='sent'), 1)

    @override_settings(MAIL_DELIVERY='inline')
    def test_an_inline_mail_is_counted_when_sent(self):
        enqueue_mail(to_email=EMAIL, subject='제목', body='본문', kind=MailKind.PASSWORD_CHANGED)

        self.assertEqual(self.metrics.value('emails_sent', kind='password_changed', result='sent'), 1)

    def test_the_worker_writes_how_many_mails_are_waiting(self):
        enqueue_mail(to_email=EMAIL, subject='제목', body='본문')
        enqueue_mail(to_email=EMAIL, subject='제목', body='본문')

        with failing_mail_server():
            call_command('send_outgoing_mail', '--once', stdout=StringIO())

        # 둘 다 다시 시도할 것으로 남았다. 바퀴는 작업 하나로 센다
        self.assertEqual(self.metrics.value('background_jobs_queued', operation='mail.deliver_outgoing'), 2)
        self.assertEqual(
            self.metrics.value('background_jobs_finished', operation='mail.deliver_outgoing', result='success'), 1
        )


@override_settings(BILLING_SECRET=SECRET)
class WithdrawalQueueTests(TestCase):
    """결제 쪽 워커(send_welcome_credits)가 바퀴의 끝에 적는 밀린 탈퇴와 알리지 못한 알림의 수."""

    def setUp(self) -> None:
        self.metrics = record_metrics(self)
        self.user = User.objects.create_user(username='player_01', email=EMAIL, nickname='플레이어', password='x' * 12)
        # 유예가 1분 전에 끝났다
        User.objects.filter(pk=self.user.pk).update(
            withdrawal_requested_at=timezone.now() - GRACE - timedelta(minutes=1)
        )

    def one_round(self) -> None:
        """워커의 한 바퀴. 결제 서버는 탈퇴 알림을 받지 않는다."""
        undelivered = WithdrawalUndeliveredError('billing 가 503 으로 답했다')
        with (
            patch('accounts.withdrawal.send_withdrawal', side_effect=undelivered),
            self.assertLogs('accounts.withdrawal', level='WARNING'),
        ):
            call_command('send_welcome_credits', '--once', stdout=StringIO())

    def queued(self, operation: str):
        return self.metrics.value('background_jobs_queued', operation=operation)

    def test_a_round_writes_what_is_left(self):
        self.one_round()

        # 이 바퀴에 비웠으니 밀린 탈퇴는 없다. 결제 서버가 받지 않아 알림 하나가 남았다
        self.assertEqual(self.queued('withdrawal.complete'), 0)
        self.assertEqual(self.queued('withdrawal.deliver'), 1)

    def test_delivered_notices_are_not_counted(self):
        with patch('accounts.withdrawal.send_withdrawal', return_value=None):
            call_command('send_welcome_credits', '--once', stdout=StringIO())

        self.assertEqual(self.queued('withdrawal.deliver'), 0)

    def test_only_servers_with_a_secret_are_counted(self):
        self.one_round()

        # 줄은 서버마다 적었지만 비밀은 결제 서버의 것뿐이다. 나머지는 받는 주소가 생길 때까지 기다리는 것이 정상이다
        self.assertGreater(WithdrawalNotice.objects.filter(delivered_at__isnull=True).count(), 1)
        self.assertEqual(self.queued('withdrawal.deliver'), 1)

    def test_an_account_still_in_its_grace_is_not_overdue(self):
        User.objects.filter(pk=self.user.pk).update(withdrawal_requested_at=timezone.now() - timedelta(days=1))

        call_command('send_welcome_credits', '--once', stdout=StringIO())

        self.assertEqual(self.queued('withdrawal.complete'), 0)

    def test_an_account_not_emptied_in_time_is_counted(self):
        # 비우지 못했다(비우다 실패하는 것과 같다)
        with patch.object(withdrawal, 'complete_due_withdrawals', return_value=0):
            call_command('send_welcome_credits', '--once', stdout=StringIO())

        self.assertEqual(self.queued('withdrawal.complete'), 1)
        self.assertEqual(self.queued('withdrawal.deliver'), 0)


@override_settings(ATTEMPT_LIMITS_ENABLED=True)
class AttemptLimitTests(SimpleTestCase):
    """실제 Redis 에서 돈다(accounts/tests/test_attempt_limits.py 와 같다)."""

    def setUp(self) -> None:
        delete_attempt_keys()
        self.addCleanup(delete_attempt_keys)
        reset_redis_breaker()
        self.addCleanup(reset_redis_breaker)
        self.metrics = record_metrics(self)

    def test_a_blocked_attempt_is_counted_by_its_limit(self):
        count_attempt(LIMIT, 'someone')
        with self.assertRaises(TooManyAttemptsError):
            count_attempt(LIMIT, 'someone')
        with self.assertRaises(TooManyAttemptsError):
            ensure_not_blocked(LIMIT, 'someone')

        self.assertEqual(self.metrics.value('auth_rate_limited', limit='test-limit'), 2)

    def test_an_attempt_let_through_without_redis_is_counted(self):
        broken = redis.ConnectionError('Connection refused')
        with patch('accounts.attempt_limits.get_redis', side_effect=broken):
            count_attempt(LIMIT, 'someone')
            ensure_not_blocked(LIMIT, 'someone')
            count_failure(LIMIT, 'someone')

        # 막지 않고 통과시켰다. 이 값이 늘면 시도 제한이 꺼져 있다
        self.assertEqual(self.metrics.value('auth_rate_limits_unavailable', limit='test-limit'), 3)
        self.assertEqual(self.metrics.points('auth_rate_limited'), [])
