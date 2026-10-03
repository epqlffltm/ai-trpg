# auth-server/accounts/tests/test_security_digest.py

"""
보안 이벤트 요약 메일과 오래된 기록의 정리를 검증한다.
"""

from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.mail import DIGEST_MAX_LISTED_EVENTS
from accounts.models import OutgoingMail, OutgoingMailStatus, SecurityEvent, SecurityEventKind, User
from accounts.outbox import deliver_due_mail, enqueue_mail
from accounts.security_digest import (
    EVENT_RETENTION,
    delete_old_security_events,
    report_new_security_events,
)
from accounts.security_events import record_security_event

OPERATOR = 'operator@example.com'
IP = '203.0.113.7'


def create_user() -> User:
    return User.objects.create_user(
        username='player_01',
        email='someone@example.com',
        nickname='플레이어',
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
    )


def record(kind: str = SecurityEventKind.LOGIN_FAILURES_LIMITED, **fields) -> SecurityEvent:
    fields.setdefault('ip', IP)
    record_security_event(kind=kind, **fields)
    return SecurityEvent.objects.latest('id')


def make_older(event: SecurityEvent, age: timedelta) -> None:
    """사건이 age 만큼 전에 일어난 것으로 바꾼다. created_at 은 저장할 때 자동으로 정해져서 따로 고친다."""
    SecurityEvent.objects.filter(pk=event.pk).update(created_at=timezone.now() - age)


@override_settings(SECURITY_DIGEST_TO=[OPERATOR])
class ReportTests(TestCase):
    def test_sends_nothing_when_there_are_no_events(self):
        reported = report_new_security_events()

        # 매번 "이상 없음" 이 오면 읽지 않게 된다
        self.assertEqual(reported, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_sends_one_mail_for_all_new_events(self):
        record()
        record(kind=SecurityEventKind.RESERVED_USERNAME_LOGIN)
        record()

        reported = report_new_security_events()

        self.assertEqual(reported, 3)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [OPERATOR])
        self.assertIn('3건', mail.outbox[0].subject)

    def test_mail_counts_events_by_kind(self):
        record()
        record()
        record(kind=SecurityEventKind.RESERVED_USERNAME_LOGIN)

        report_new_security_events()

        body = mail.outbox[0].body
        self.assertIn(f'{SecurityEventKind.LOGIN_FAILURES_LIMITED.label}: 2건', body)
        self.assertIn(f'{SecurityEventKind.RESERVED_USERNAME_LOGIN.label}: 1건', body)

    def test_mail_lists_the_ip_and_the_account(self):
        record(user=create_user())

        report_new_security_events()

        body = mail.outbox[0].body
        self.assertIn(IP, body)
        self.assertIn('계정 player_01', body)

    def test_events_are_reported_only_once(self):
        record()
        report_new_security_events()
        mail.outbox.clear()

        reported = report_new_security_events()

        self.assertEqual(reported, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_marks_events_as_reported(self):
        event = record()

        report_new_security_events()

        event.refresh_from_db()
        self.assertIsNotNone(event.reported_at)

    def test_events_recorded_later_go_into_the_next_mail(self):
        record()
        report_new_security_events()
        mail.outbox.clear()
        record(kind=SecurityEventKind.SIGNUP_IP_LIMITED)

        reported = report_new_security_events()

        self.assertEqual(reported, 1)
        self.assertIn(SecurityEventKind.SIGNUP_IP_LIMITED.label, mail.outbox[0].body)
        self.assertNotIn(SecurityEventKind.LOGIN_FAILURES_LIMITED.label, mail.outbox[0].body)

    def test_old_unreported_events_are_not_missed(self):
        # 요약이 한동안 돌지 않았다. 시간으로 잘랐다면 빠졌을 사건이다
        make_older(record(), timedelta(days=3))

        self.assertEqual(report_new_security_events(), 1)

    def test_long_lists_are_cut(self):
        for _ in range(DIGEST_MAX_LISTED_EVENTS + 7):
            record()

        report_new_security_events()

        body = mail.outbox[0].body
        self.assertIn(f'{DIGEST_MAX_LISTED_EVENTS + 7}건', mail.outbox[0].subject)
        self.assertIn('앞선 7건은', body)
        self.assertEqual(body.count(IP), DIGEST_MAX_LISTED_EVENTS)

    @override_settings(SECURITY_DIGEST_TO=[OPERATOR, 'second@example.com'])
    def test_sends_to_every_operator(self):
        record()

        report_new_security_events()

        self.assertEqual([message.to for message in mail.outbox], [[OPERATOR], ['second@example.com']])

    @override_settings(SECURITY_DIGEST_TO=[])
    def test_does_nothing_without_recipients(self):
        event = record()

        reported = report_new_security_events()

        # 알리지 않은 채로 남는다. 받는 사람을 나중에 정하면 그때 알린다
        event.refresh_from_db()
        self.assertEqual(reported, 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(event.reported_at)

    @override_settings(MAIL_DELIVERY='outbox')
    def test_goes_through_the_outbox(self):
        record()

        report_new_security_events()

        # 요청을 처리하는 쪽과 같은 길로 나간다. 메일 서버가 죽어 있어도 재시도된다
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(OutgoingMail.objects.get().to_email, OPERATOR)


@override_settings(MAIL_DELIVERY='outbox')
class DiscardedMailEventTests(TestCase):
    """보내지 못하고 버린 메일은 보안 이벤트로 남아, 다음 요약 메일에 실린다."""

    def discard_a_mail(self) -> None:
        enqueue_mail(to_email='someone@example.com', subject='제목', body='본문 123456')
        OutgoingMail.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        # 버릴 때 오류 로그가 남는다. 테스트 출력에 섞이지 않게 받아 둔다
        with self.assertLogs('accounts.outbox', level='ERROR'):
            deliver_due_mail()

    def test_discarding_a_mail_records_an_event(self):
        self.discard_a_mail()

        event = SecurityEvent.objects.get()
        self.assertEqual(OutgoingMail.objects.get().status, OutgoingMailStatus.DISCARDED)
        self.assertEqual(event.kind, SecurityEventKind.MAIL_DISCARDED)
        self.assertEqual(event.ip, '')
        self.assertIsNone(event.user)

    def test_sent_mail_records_nothing(self):
        enqueue_mail(to_email='someone@example.com', subject='제목', body='본문')

        deliver_due_mail()

        self.assertEqual(SecurityEvent.objects.count(), 0)

    @override_settings(SECURITY_DIGEST_TO=[OPERATOR])
    def test_event_does_not_contain_the_recipient(self):
        self.discard_a_mail()

        report_new_security_events()

        # 누구의 메일이었는지는 요약에 적지 않는다. 관리자 화면에서 확인한다
        digest = OutgoingMail.objects.get(to_email=OPERATOR)
        self.assertIn(SecurityEventKind.MAIL_DISCARDED.label, digest.body)
        self.assertNotIn('someone@example.com', digest.body)


class CleanupTests(TestCase):
    def test_deletes_events_past_the_retention(self):
        old = record()
        make_older(old, EVENT_RETENTION + timedelta(minutes=1))
        recent = record()
        make_older(recent, EVENT_RETENTION - timedelta(minutes=1))

        deleted = delete_old_security_events()

        self.assertEqual(deleted, 1)
        self.assertEqual(list(SecurityEvent.objects.all()), [recent])

    def test_deletes_old_events_even_if_never_reported(self):
        make_older(record(), EVENT_RETENTION + timedelta(days=1))

        # 받는 사람이 없어 알리지 못한 사건이 영영 쌓이지 않게 한다
        self.assertEqual(delete_old_security_events(), 1)


class CommandTests(TestCase):
    def run_command(self) -> str:
        output = StringIO()
        call_command('send_security_digest', stdout=output)
        return output.getvalue()

    @override_settings(SECURITY_DIGEST_TO=[OPERATOR])
    def test_reports_and_cleans_up(self):
        record()
        make_older(record(), EVENT_RETENTION + timedelta(days=1))

        output = self.run_command()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(SecurityEvent.objects.count(), 1)
        self.assertIn('알린 보안 이벤트 2건', output)
        self.assertIn('지운 오래된 기록 1건', output)

    @override_settings(SECURITY_DIGEST_TO=[])
    def test_says_so_when_there_are_no_recipients(self):
        record()

        output = self.run_command()

        self.assertEqual(len(mail.outbox), 0)
        self.assertIn('SECURITY_DIGEST_TO', output)
        self.assertIn('알린 보안 이벤트 0건', output)
