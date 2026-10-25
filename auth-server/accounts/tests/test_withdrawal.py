# auth-server/accounts/tests/test_withdrawal.py

"""
탈퇴(#603, docs/architecture/withdrawal.md)를 검증한다.

  - 요청: 비밀번호를 확인하고, 모든 세션을 끊고, 메일과 보안 이벤트를 남긴다. 다시 눌러도 유예가 늘지 않는다
  - 유예: 다시 로그인하면 토큰이 인증 서버에만 통한다. 취소하면 갱신부터 모든 서버에 통한다
  - 하루 전 알림(#624): 마치기 하루 전에 한 통을 더 보낸다. 요청마다 한 통이다. 늦어도 마치기 전에만 보내고,
    마치는 시각은 그대로다. 나가지 못한 알림은 마칠 때 지운다
  - 마치기: 7일이 지나면 계정을 비우고, 지우기 전의 주소로 메일을 보내고, 결제 서버에 알릴 줄을 적는다
  - 알리기: 모든 서버에 줄을 적고, 비밀을 적은 서버에만 받을 때까지 다시 보낸다. 받으면 끝이다
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

import jwt
from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.erasure import is_removed_account
from accounts.identity import verify_identity
from accounts.management.commands.send_welcome_credits import WithdrawalRound
from accounts.models import (
    ConsentRecord,
    IdentityVerification,
    MailKind,
    OutgoingMail,
    PaymentEligibility,
    SecurityEvent,
    SecurityEventKind,
    Suspension,
    SuspensionReason,
    User,
    WelcomeCredit,
    WithdrawalNotice,
    WithdrawalTarget,
)
from accounts.suspension import suspend_account
from accounts.tests.billing_stub import SECRET
from accounts.tests.helpers import BrowserClient, agree_to_required, identity_token, log_in
from accounts.tokens import issue_token_pair
from accounts.withdrawal import (
    LEASE,
    REMINDER_LEAD,
    cancel_withdrawal,
    complete_due_withdrawals,
    complete_withdrawal,
    deliver_due_withdrawal_notices,
    remind_due_withdrawals,
    remind_withdrawal,
    request_withdrawal,
)
from accounts.withdrawal_client import WithdrawalUndeliveredError
from accounts.withdrawal_schedule import GRACE

WITHDRAWAL_URL = reverse('accounts:my-withdrawal')
ME_URL = reverse('accounts:me')
REFRESH_URL = reverse('accounts:refresh')

PASSWORD = 'correct-horse-battery'
EMAIL = 'someone@example.com'
GAME_SERVER = 'ai-trpg-game'


def make_user() -> User:
    """필수 항목에 동의한, 로그인할 수 있는 계정."""
    user = User.objects.create_user(
        username='player_01', email=EMAIL, nickname='플레이어', password=PASSWORD, email_verified_at=timezone.now()
    )
    agree_to_required(user)
    return user


def audience_of(access_token: str) -> list[str]:
    return jwt.decode(access_token, options={'verify_signature': False})['aud']


def at(moment):
    """탈퇴 쪽의 시계를 moment 로 맞춘다."""
    return patch('accounts.withdrawal.timezone.now', return_value=moment)


def servers_answer(*outcomes):
    """
    알림을 받는 서버가 차례로 이렇게 답하는 상황을 만든다. None 이면 받았다, 예외면 그 예외를 낸다.

    바꿔 끼우는 것(with 에 쓴다)과 가짜(받은 것을 calls 에 적는다)를 함께 돌려준다.
    """
    fake = _answering(list(outcomes))
    return patch('accounts.withdrawal.send_withdrawal', fake), fake


def _answering(outcomes: list):
    calls = []

    def send(**kwargs):
        calls.append(kwargs)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    send.calls = calls
    return send


class RequestTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.access = issue_token_pair(self.user).access
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access}')

    def request_withdrawal(self, password: str = PASSWORD):
        return self.client.post(WITHDRAWAL_URL, {'password': password}, format='json')

    def test_a_wrong_password_changes_nothing(self):
        response = self.request_withdrawal('wrong-password-123')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data['errors'])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.withdrawal_requested_at)
        # 세션도 그대로다
        self.assertEqual(self.client.get(ME_URL).status_code, status.HTTP_200_OK)

    def test_needs_a_login(self):
        self.client.credentials()

        self.assertEqual(self.request_withdrawal().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_schedules_the_erasure_and_ends_every_session(self):
        before = timezone.now()

        response = self.request_withdrawal()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.user.refresh_from_db()
        self.assertGreaterEqual(self.user.withdrawal_requested_at, before)
        scheduled = (self.user.withdrawal_requested_at + GRACE).isoformat().replace('+00:00', 'Z')
        self.assertEqual(response.data['withdrawal_scheduled_at'], scheduled)
        # 이 요청의 토큰도 끊겼다. 화면은 로그인 화면으로 간다
        self.assertEqual(self.client.get(ME_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.cookies[REFRESH_COOKIE_NAME].value, '')

    def test_tells_the_owner_and_the_operator(self):
        self.request_withdrawal()

        # 빼앗긴 계정이면 진짜 주인이 메일을 보고 취소한다
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertIn('탈퇴 요청', mail.outbox[0].subject)
        self.assertIn('취소', mail.outbox[0].body)
        self.assertIn('하루 전에 한 번 더', mail.outbox[0].body)
        self.assertTrue(
            SecurityEvent.objects.filter(kind=SecurityEventKind.WITHDRAWAL_REQUESTED, user=self.user).exists()
        )

    def test_asking_again_does_not_push_the_date(self):
        first = self.request_withdrawal()
        # 요청으로 세션 버전이 올랐다. 다시 로그인한 것과 같은 토큰이다
        self.user.refresh_from_db()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {issue_token_pair(self.user).access}')

        again = self.request_withdrawal()

        self.assertEqual(again.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(again.data['withdrawal_scheduled_at'], first.data['withdrawal_scheduled_at'])
        self.assertEqual(len(mail.outbox), 1)


class GraceTests(APITestCase):
    """유예 동안의 로그인, 취소, 갱신."""

    client_class = BrowserClient

    def setUp(self):
        self.user = make_user()
        access = issue_token_pair(self.user).access
        response = self.client.post(
            WITHDRAWAL_URL, {'password': PASSWORD}, format='json', HTTP_AUTHORIZATION=f'Bearer {access}'
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.scheduled = response.data['withdrawal_scheduled_at']

    def test_logging_in_again_opens_only_this_server(self):
        response = log_in(self.client, 'player_01', PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['withdrawal_scheduled_at'], self.scheduled)
        self.assertEqual(audience_of(response.data['access_token']), [settings.JWT_OWN_AUDIENCE])
        me = self.client.get(ME_URL, HTTP_AUTHORIZATION=f'Bearer {response.data["access_token"]}')
        self.assertEqual(me.json()['withdrawal_scheduled_at'], self.scheduled)

    def test_cancelling_brings_every_server_back(self):
        access = log_in(self.client, 'player_01', PASSWORD).data['access_token']

        cancelled = self.client.delete(WITHDRAWAL_URL, HTTP_AUTHORIZATION=f'Bearer {access}')
        refreshed = self.client.post(REFRESH_URL)

        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertIsNone(cancelled.data['withdrawal_scheduled_at'])
        self.assertIsNone(refreshed.data['withdrawal_scheduled_at'])
        self.assertIn(GAME_SERVER, audience_of(refreshed.data['access_token']))
        self.user.refresh_from_db()
        self.assertIsNone(self.user.withdrawal_requested_at)

    def test_cancelling_without_a_request_is_fine(self):
        other = User.objects.create_user(
            username='player_02', email='other@example.com', nickname='둘', password=PASSWORD
        )

        response = self.client.delete(WITHDRAWAL_URL, HTTP_AUTHORIZATION=f'Bearer {issue_token_pair(other).access}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(BILLING_SECRET=SECRET)
class CompleteTests(TestCase):
    def setUp(self):
        self.user = make_user()
        verify_identity(user=self.user, token=identity_token('person-1'))
        with at(timezone.now()):
            request_withdrawal(self.user)
        self.user.refresh_from_db()
        self.due = self.user.withdrawal_requested_at + GRACE
        mail.outbox.clear()

    def complete_at(self, moment) -> int:
        with at(moment):
            return complete_due_withdrawals()

    def test_nothing_happens_before_the_grace_ends(self):
        self.assertEqual(self.complete_at(self.due - timedelta(seconds=1)), 0)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.withdrawn_at)

    def test_empties_the_account_when_the_grace_ends(self):
        self.assertEqual(self.complete_at(self.due), 1)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(is_removed_account(self.user))
        self.assertNotIn('someone', self.user.email)
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(self.user.withdrawn_at, self.due)
        # 사람을 알아볼 수 있는 기록을 지운다
        self.assertFalse(IdentityVerification.objects.filter(user=self.user).exists())
        self.assertFalse(PaymentEligibility.objects.filter(user=self.user).exists())
        self.assertFalse(ConsentRecord.objects.filter(user=self.user).exists())
        # 같은 사람이 계정을 바꿔 환영 크레딧을 다시 받지 못하게 남긴다
        self.assertTrue(WelcomeCredit.objects.filter(user_public_id=self.user.public_id).exists())

    def test_tells_the_old_address_and_queues_a_notice_for_every_server(self):
        self.complete_at(self.due)

        self.assertEqual([message.to for message in mail.outbox], [[EMAIL]])
        self.assertIn('탈퇴를 마쳤습니다', mail.outbox[0].subject)
        # 비밀을 아직 적지 않은 서버의 줄도 적는다. 받는 주소를 만들고 비밀을 적으면 그때 나간다
        notices = WithdrawalNotice.objects.filter(user=self.user)
        self.assertEqual({notice.target for notice in notices}, set(WithdrawalTarget))
        self.assertTrue(all(n.withdrawn_at == self.due and n.delivered_at is None for n in notices))
        self.assertTrue(SecurityEvent.objects.filter(kind=SecurityEventKind.ACCOUNT_WITHDRAWN, user=self.user).exists())

    def test_a_finished_account_cannot_log_in(self):
        self.complete_at(self.due)

        response = BrowserClient().post(
            reverse('accounts:login'), {'username': 'player_01', 'password': PASSWORD}, format='json'
        )

        self.assertNotEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_finishing_twice_does_it_once(self):
        self.assertEqual(self.complete_at(self.due), 1)
        self.assertEqual(self.complete_at(self.due + timedelta(days=1)), 0)

        self.assertEqual(WithdrawalNotice.objects.filter(user=self.user).count(), len(WithdrawalTarget))
        self.assertEqual(len(mail.outbox), 1)

    def test_a_finished_account_is_not_finished_again(self):
        # 정리 작업 둘이 같은 계정을 골랐다. 뒤의 것은 잠근 뒤 마친 것을 보고 그만둔다
        self.assertTrue(complete_withdrawal(self.user.pk, self.due))

        self.assertFalse(complete_withdrawal(self.user.pk, self.due + timedelta(hours=1)))
        self.assertEqual(WithdrawalNotice.objects.filter(user=self.user).count(), len(WithdrawalTarget))

    def test_a_request_made_again_waits_its_own_grace(self):
        # 정리 작업이 고른 뒤 잠그기 전에 취소하고 다시 요청했다. 새 요청의 유예가 지나지 않았으니 비우지 않는다
        User.objects.filter(pk=self.user.pk).update(withdrawal_requested_at=self.due)

        self.assertFalse(complete_withdrawal(self.user.pk, self.due))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_a_cancelled_request_is_not_finished(self):
        # 정리 작업이 고른 뒤 잠그기 전에 취소한 것과 같다. 잠근 뒤 다시 보므로 비우지 않는다
        User.objects.filter(pk=self.user.pk).update(withdrawal_requested_at=None)

        self.assertFalse(complete_withdrawal(self.user.pk, self.due))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_an_account_suspended_during_the_grace_is_still_emptied(self):
        # 정지는 탈퇴를 멈추지 않는다(withdrawal.md 의 "정한 것"). 정지된 사람의 개인정보를 쥐고 있지 않는다
        suspend_account(self.user, '도배', reason=SuspensionReason.SPAM)

        self.assertEqual(self.complete_at(self.due), 1)
        self.user.refresh_from_db()
        self.assertTrue(is_removed_account(self.user))
        self.assertEqual(self.user.withdrawn_at, self.due)
        # 운영자가 적은 사유도 그 사람에 관한 글이라 지운다(#634)
        self.assertFalse(Suspension.objects.filter(user=self.user).exists())


class RemindTests(TestCase):
    """마치기 하루 전의 알림(#624)."""

    def setUp(self):
        self.user = make_user()
        with at(timezone.now()):
            request_withdrawal(self.user)
        self.user.refresh_from_db()
        self.due = self.user.withdrawal_requested_at + GRACE
        mail.outbox.clear()

    def remind_at(self, moment, **options) -> int:
        with at(moment):
            return remind_due_withdrawals(**options)

    def earlier_request(self, before, **fields) -> User:
        """이 계정보다 before 만큼 먼저 탈퇴를 요청한 다른 계정. 고르는 차례가 앞선다."""
        other = User.objects.create_user(
            username='player_02', email='other@example.com', nickname='둘', password=PASSWORD
        )
        User.objects.filter(pk=other.pk).update(
            withdrawal_requested_at=self.user.withdrawal_requested_at - before, **fields
        )
        return other

    def reminders(self) -> list:
        return [message for message in mail.outbox if '계정을 지웁니다' in message.subject]

    def test_nothing_is_sent_before_the_day_before(self):
        # 요청에서 6일이 하루 전이다
        self.assertEqual(self.remind_at(self.user.withdrawal_requested_at + timedelta(days=6, seconds=-1)), 0)

        self.assertEqual(mail.outbox, [])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.withdrawal_reminded_at)

    def test_tells_the_owner_a_day_before(self):
        self.assertEqual(self.remind_at(self.user.withdrawal_requested_at + timedelta(days=6)), 1)

        (message,) = mail.outbox
        self.assertEqual(message.to, [EMAIL])
        # "내일"이 아니라 지우는 시각을 적는다(한국 시각)
        when = self.due.astimezone(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M')
        self.assertIn(when, message.subject)
        self.assertIn(when, message.body)
        # 빼앗긴 계정이면 진짜 주인이 마지막으로 알 기회다
        self.assertIn('로그인하면 탈퇴를 취소', message.body)
        self.assertIn('비밀번호를 바꿔', message.body)
        self.user.refresh_from_db()
        self.assertEqual(self.user.withdrawal_reminded_at, self.due - REMINDER_LEAD)

    def test_one_mail_per_request_however_often_the_worker_runs(self):
        for moment in (self.due - REMINDER_LEAD, self.due - timedelta(hours=12), self.due - timedelta(seconds=1)):
            self.remind_at(moment)

        self.assertEqual(len(self.reminders()), 1)

    def test_a_late_worker_still_reminds_and_the_end_does_not_move(self):
        # 워커가 멈췄다가 마치기 1분 전에 다시 떴다. 보내되 마치는 시각은 늦추지 않는다
        self.assertEqual(self.remind_at(self.due - timedelta(minutes=1)), 1)

        with at(self.due):
            self.assertEqual(complete_due_withdrawals(), 1)
        self.user.refresh_from_db()
        self.assertEqual(self.user.withdrawn_at, self.due)

    def test_no_reminder_once_the_end_has_come(self):
        # 워커가 마칠 때가 지나서 떴다. 같은 바퀴에 마치므로 "곧 지운다"를 보내지 않는다
        self.assertEqual(self.remind_at(self.due), 0)
        self.assertEqual(self.remind_at(self.due + timedelta(days=1)), 0)

        self.assertEqual(mail.outbox, [])

    def test_a_finished_account_is_not_reminded(self):
        # 마친 계정의 요청 시각이 하루 전의 범위에 있어도(관리자의 실수) 보내지 않고, 고르는 묶음도 채우지 않는다
        self.earlier_request(timedelta(hours=1), withdrawn_at=self.due - REMINDER_LEAD - timedelta(hours=2))

        self.assertEqual(self.remind_at(self.due - REMINDER_LEAD, batch_size=1), 1)
        self.assertEqual([message.to for message in mail.outbox], [[EMAIL]])

    def test_accounts_already_reminded_do_not_fill_the_batch(self):
        self.earlier_request(timedelta(hours=1), withdrawal_reminded_at=self.due - REMINDER_LEAD - timedelta(hours=1))

        self.assertEqual(self.remind_at(self.due - REMINDER_LEAD, batch_size=1), 1)
        self.assertEqual([message.to for message in mail.outbox], [[EMAIL]])

    def test_accounts_at_their_end_do_not_fill_the_batch(self):
        # 마칠 때가 막 된 계정(같은 바퀴에 마친다)이 앞에 있어도 이 계정에 보낸다
        self.earlier_request(REMINDER_LEAD)

        self.assertEqual(self.remind_at(self.due - REMINDER_LEAD, batch_size=1), 1)
        self.assertEqual([message.to for message in mail.outbox], [[EMAIL]])

    def test_a_cancelled_request_is_not_reminded(self):
        cancel_withdrawal(self.user)

        self.assertEqual(self.remind_at(self.due - REMINDER_LEAD), 0)
        self.assertEqual(mail.outbox, [])

    def test_a_request_cancelled_after_the_pick_is_not_reminded(self):
        # 워커가 고른 뒤 잠그기 전에 취소했다. 잠근 뒤 다시 보므로 보내지 않는다
        User.objects.filter(pk=self.user.pk).update(withdrawal_requested_at=None)

        self.assertFalse(remind_withdrawal(self.user.pk, self.due - REMINDER_LEAD))
        self.assertEqual(mail.outbox, [])

    def test_a_worker_that_locks_at_the_end_does_not_remind(self):
        # 마치기 전에 골랐는데 잠갔을 때는 마칠 때가 되었다. 같은 바퀴에 마치므로 보내지 않는다
        self.assertFalse(remind_withdrawal(self.user.pk, self.due))
        self.assertEqual(mail.outbox, [])

    def test_only_the_mails_sent_are_counted(self):
        # 고른 계정을 다른 워커가 먼저 보냈다
        with patch('accounts.withdrawal.remind_withdrawal', return_value=False):
            self.assertEqual(self.remind_at(self.due - REMINDER_LEAD), 0)

    def test_two_workers_send_one_mail(self):
        # 둘이 같은 계정을 골랐다. 뒤의 것은 잠근 뒤 보낸 것을 보고 그만둔다
        self.assertTrue(remind_withdrawal(self.user.pk, self.due - REMINDER_LEAD))

        self.assertFalse(remind_withdrawal(self.user.pk, self.due - REMINDER_LEAD + timedelta(seconds=1)))
        self.assertEqual(len(mail.outbox), 1)

    def test_a_new_request_after_cancelling_gets_its_own_reminder(self):
        self.remind_at(self.due - REMINDER_LEAD)
        cancel_withdrawal(self.user)
        again = self.due - REMINDER_LEAD + timedelta(hours=1)
        with at(again):
            request_withdrawal(self.user)
        new_due = again + GRACE

        early = self.remind_at(new_due - REMINDER_LEAD - timedelta(seconds=1))
        on_time = self.remind_at(new_due - REMINDER_LEAD)
        later = self.remind_at(new_due - timedelta(seconds=1))

        self.assertEqual((early, on_time, later), (0, 1, 0))
        self.assertEqual(len(self.reminders()), 2)

    @override_settings(MAIL_DELIVERY='outbox')
    def test_a_reminder_not_yet_sent_is_dropped_when_the_account_is_emptied(self):
        # 메일 서버가 멈춰 알림이 발송함에 남은 채 마칠 때가 왔다. 마친 뒤에 "곧 지운다"가 가지 않는다
        self.remind_at(self.due - timedelta(minutes=1))
        self.assertEqual(OutgoingMail.objects.filter(kind=MailKind.WITHDRAWAL_REMINDER).count(), 1)

        with at(self.due):
            complete_due_withdrawals()

        self.assertEqual(list(OutgoingMail.objects.values_list('kind', flat=True)), [MailKind.WITHDRAWAL_COMPLETED])


@override_settings(BILLING_SECRET=SECRET)
class DeliverTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.now = timezone.now()
        User.objects.filter(pk=self.user.pk).update(withdrawal_requested_at=self.now - GRACE)
        with at(self.now):
            complete_due_withdrawals()
        self.notice = WithdrawalNotice.objects.get(user=self.user, target=WithdrawalTarget.BILLING)

    def deliver_at(self, moment):
        with at(moment):
            return deliver_due_withdrawal_notices()

    def test_tells_only_the_servers_with_a_secret(self):
        # 비밀은 결제 서버의 것뿐이다. 다른 서버의 줄은 비밀을 적을 때까지 기다린다
        answers, fake = servers_answer(None)
        with answers:
            report = self.deliver_at(self.now)

        self.assertEqual((report.sent, report.retried), (1, 0))
        self.assertEqual(
            fake.calls,
            [{'target': 'billing', 'user_public_id': self.user.public_id, 'withdrawn_at': self.now}],
        )
        self.notice.refresh_from_db()
        self.assertEqual(self.notice.delivered_at, self.now)

    def test_keeps_trying_until_billing_answers(self):
        with (
            servers_answer(WithdrawalUndeliveredError('billing 가 404 로 답했다'), None)[0],
            self.assertLogs('accounts.withdrawal', level='WARNING'),
        ):
            first = self.deliver_at(self.now)
            # 다시 보낼 시각 전에는 보내지 않는다
            idle = self.deliver_at(self.now + timedelta(seconds=1))
            second = self.deliver_at(self.now + timedelta(minutes=1))

        self.assertEqual((first.retried, idle.handled, second.sent), (1, 0, 1))
        self.notice.refresh_from_db()
        self.assertIsNotNone(self.notice.delivered_at)
        self.assertEqual(self.notice.attempts, 0)

    def test_a_server_whose_secret_is_written_later_gets_the_old_notices(self):
        with servers_answer(None)[0]:
            self.deliver_at(self.now)
        answers, fake = servers_answer(None)

        # 게임 서버가 받는 주소를 만들고 비밀을 적었다. 그 전에 탈퇴한 사람의 것도 받는다
        with override_settings(GAME_SECRET=SECRET), answers:
            report = self.deliver_at(self.now + timedelta(days=30))

        self.assertEqual((report.sent, [call['target'] for call in fake.calls]), (1, ['game']))

    def test_a_delivered_notice_is_not_sent_again(self):
        with servers_answer(None)[0]:
            self.deliver_at(self.now)

        self.assertEqual(self.deliver_at(self.now + timedelta(days=1)).handled, 0)

    def test_a_notice_left_by_a_dead_worker_goes_out_after_the_lease(self):
        # 차지한 워커가 보내다 죽었다. 임대가 끝나면 다른 워커가 다시 보낸다(받는 쪽은 두 번 받아도 같다)
        WithdrawalNotice.objects.filter(pk=self.notice.pk).update(next_attempt_at=self.now + LEASE)

        with servers_answer(None)[0]:
            early = self.deliver_at(self.now + LEASE - timedelta(seconds=1))
            late = self.deliver_at(self.now + LEASE)

        self.assertEqual((early.handled, late.sent), (0, 1))


@override_settings(BILLING_SECRET=SECRET)
class WorkerTests(TestCase):
    def test_one_round_finishes_and_tells(self):
        user = make_user()
        User.objects.filter(pk=user.pk).update(withdrawal_requested_at=timezone.now() - GRACE - timedelta(minutes=1))
        output = StringIO()

        with servers_answer(None)[0]:
            call_command('send_welcome_credits', '--once', stdout=output)

        # 마친 계정의 알림이 같은 바퀴에 나간다. 마칠 때가 지났으므로 하루 전 알림은 보내지 않는다
        self.assertIn('탈퇴 하루 전 메일 0건, 탈퇴를 마친 계정 1건, 탈퇴 알림 1건', output.getvalue())
        self.assertIsNotNone(WithdrawalNotice.objects.get(user=user, target=WithdrawalTarget.BILLING).delivered_at)
        self.assertEqual([message.subject for message in mail.outbox], ['[AI TRPG] 탈퇴를 마쳤습니다'])

    def test_a_round_that_reminded_is_not_idle(self):
        # 보낸 것이 있으면 워커가 쉬지 않고 다음 묶음을 본다
        self.assertEqual(WithdrawalRound(reminded=1).done, 1)

    def test_one_round_reminds_a_day_before(self):
        user = make_user()
        requested = timezone.now() - (GRACE - REMINDER_LEAD) - timedelta(minutes=1)
        User.objects.filter(pk=user.pk).update(withdrawal_requested_at=requested)
        output = StringIO()

        call_command('send_welcome_credits', '--once', stdout=output)

        self.assertIn('탈퇴 하루 전 메일 1건, 탈퇴를 마친 계정 0건', output.getvalue())
        self.assertEqual([message.to for message in mail.outbox], [[EMAIL]])
        user.refresh_from_db()
        self.assertIsNone(user.withdrawn_at)
