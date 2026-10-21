# auth-server/accounts/tests/test_withdrawal.py

"""
탈퇴(#603, docs/architecture/withdrawal.md)를 검증한다.

  - 요청: 비밀번호를 확인하고, 모든 세션을 끊고, 메일과 보안 이벤트를 남긴다. 다시 눌러도 유예가 늘지 않는다
  - 유예: 다시 로그인하면 토큰이 인증 서버에만 통한다. 취소하면 갱신부터 모든 서버에 통한다
  - 마치기: 7일이 지나면 계정을 비우고, 지우기 전의 주소로 메일을 보내고, 결제 서버에 알릴 줄을 적는다
  - 알리기: 모든 서버에 줄을 적고, 비밀을 적은 서버에만 받을 때까지 다시 보낸다. 받으면 끝이다
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

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
from accounts.models import (
    ConsentRecord,
    IdentityVerification,
    PaymentEligibility,
    SecurityEvent,
    SecurityEventKind,
    User,
    WelcomeCredit,
    WithdrawalNotice,
    WithdrawalTarget,
)
from accounts.tests.billing_stub import SECRET
from accounts.tests.helpers import BrowserClient, agree_to_required, identity_token, log_in
from accounts.tokens import issue_token_pair
from accounts.withdrawal import (
    LEASE,
    complete_due_withdrawals,
    complete_withdrawal,
    deliver_due_withdrawal_notices,
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
        self.assertIn('password', response.data)
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

        # 마친 계정의 알림이 같은 바퀴에 나간다
        self.assertIn('탈퇴를 마친 계정 1건, 탈퇴 알림 1건', output.getvalue())
        self.assertIsNotNone(WithdrawalNotice.objects.get(user=user, target=WithdrawalTarget.BILLING).delivered_at)
