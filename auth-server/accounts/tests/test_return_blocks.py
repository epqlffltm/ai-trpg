# auth-server/accounts/tests/test_return_blocks.py

"""
정지된 채 탈퇴한 사람의 재가입 막기(#634, accounts/return_blocks.py)를 검증한다.

  - 남기기: 탈퇴를 마칠 때 정지 중이면 본인인증과 이메일의 값을 사유의 기간으로 남긴다. 정지 중이 아니면 남기지 않는다
  - 본인인증: 막힌 사람이면 403 identity_blocked 다. 사유가 spam·other 면 인증만 거절,
    abuse·fraud·illegal 이면 새 계정도 정지한다
  - 가입 1단계: 막힌 이메일이면 응답은 같은 202 이고, 코드 대신 가입을 받지 않는다는 메일이 간다
  - 지우기: 기간이 지난 값은 막지 않고, 정리가 지운다. 운영자는 관리 화면에서 지운다
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.identity import RETURN_SUSPENSION_NOTE, IdentityBlockedError, person_key, verify_identity
from accounts.models import (
    IdentityVerification,
    ReturnBlock,
    ReturnBlockKind,
    SecurityEvent,
    SecurityEventKind,
    SignupCode,
    Suspension,
    SuspensionReason,
    User,
    WelcomeCredit,
)
from accounts.return_blocks import (
    POLICIES,
    IdentityRule,
    active_block,
    delete_expired_blocks,
    email_key,
    record_return_blocks,
)
from accounts.suspension import restore_account, suspend_account
from accounts.tests.billing_stub import SECRET
from accounts.tests.helpers import SIGNUP_URL, agree_to_required, authorize, identity_token
from accounts.tests.helpers import verify_identity as post_identity
from accounts.withdrawal import complete_due_withdrawals
from accounts.withdrawal_schedule import GRACE

EMAIL = 'leaver@example.com'
PERSON = 'person-1'
PASSWORD = 'correct-horse-battery'


def make_user(username: str = 'player_01', email: str = EMAIL) -> User:
    """필수 항목에 동의한, 로그인할 수 있는 계정."""
    user = User.objects.create_user(
        username=username, email=email, nickname=username, password=PASSWORD, email_verified_at=timezone.now()
    )
    agree_to_required(user)
    return user


def block(kind: str, key: str, reason: str, expires_at) -> ReturnBlock:
    return ReturnBlock.objects.create(kind=kind, key=key, reason=reason, expires_at=expires_at)


def blocks() -> dict[str, ReturnBlock]:
    """남긴 값을 종류마다."""
    return {row.kind: row for row in ReturnBlock.objects.all()}


class PolicyTests(TestCase):
    def test_every_reason_has_a_rule(self):
        self.assertEqual(set(POLICIES), set(SuspensionReason.values))

    def test_the_rules_follow_the_table_of_the_issue(self):
        # #634 의 사유 표. 바꾸면 처리방침의 기간도 함께 고친다
        table = {reason: (policy.identity, policy.keep_for.days) for reason, policy in POLICIES.items()}
        self.assertEqual(
            table,
            {
                'spam': (IdentityRule.REFUSE, 183),
                'abuse': (IdentityRule.SUSPEND, 365),
                'fraud': (IdentityRule.SUSPEND, 1095),
                'illegal': (IdentityRule.SUSPEND, 1825),
                'other': (IdentityRule.REFUSE, 365),
            },
        )

    def test_the_email_value_ignores_case_and_spaces(self):
        self.assertEqual(email_key(' Leaver@Example.COM '), email_key(EMAIL))
        self.assertNotEqual(email_key(EMAIL), email_key('other@example.com'))
        # 사람 열쇠와 섞는 값이 다르다. 같은 글자여도 겹치지 않는다
        self.assertNotEqual(email_key(EMAIL), person_key(EMAIL))


@override_settings(BILLING_SECRET=SECRET)
class RecordTests(TestCase):
    """탈퇴를 마칠 때 남기기."""

    def setUp(self):
        self.user = make_user()
        self.now = timezone.now()
        User.objects.filter(pk=self.user.pk).update(withdrawal_requested_at=self.now - GRACE)

    def complete(self) -> None:
        with patch('accounts.withdrawal.timezone.now', return_value=self.now):
            self.assertEqual(complete_due_withdrawals(), 1)

    def test_a_suspended_and_verified_account_leaves_both_values(self):
        verify_identity(user=self.user, token=identity_token(PERSON))
        suspend_account(self.user, '결제 사기', reason=SuspensionReason.FRAUD)

        self.complete()

        left = blocks()
        self.assertEqual(set(left), {ReturnBlockKind.IDENTITY, ReturnBlockKind.EMAIL})
        self.assertEqual(left[ReturnBlockKind.IDENTITY].key, person_key(PERSON))
        self.assertEqual(left[ReturnBlockKind.EMAIL].key, email_key(EMAIL))
        for row in left.values():
            self.assertEqual((row.reason, row.expires_at), ('fraud', self.now + timedelta(days=1095)))
        # 남긴 것은 서명한 값뿐이다. 계정의 기록은 지웠다
        self.assertFalse(IdentityVerification.objects.filter(user=self.user).exists())
        self.assertFalse(Suspension.objects.filter(user=self.user).exists())

    def test_an_account_without_identity_leaves_only_the_email(self):
        suspend_account(self.user, '도배', reason=SuspensionReason.SPAM)

        self.complete()

        self.assertEqual(set(blocks()), {ReturnBlockKind.EMAIL})

    def test_an_account_that_is_not_suspended_leaves_nothing(self):
        verify_identity(user=self.user, token=identity_token(PERSON))

        self.complete()

        self.assertEqual(blocks(), {})

    def test_a_restored_account_leaves_nothing(self):
        suspend_account(self.user, '도배', reason=SuspensionReason.SPAM)
        restore_account(self.user, '신고 오인')

        self.complete()

        self.assertEqual(blocks(), {})

    def test_a_later_block_is_not_shortened(self):
        # 앞서 다른 계정에서 정지된 채 탈퇴한 같은 주소다. 남은 기간이 더 길다
        later = self.now + timedelta(days=2000)
        block(ReturnBlockKind.EMAIL, email_key(EMAIL), 'illegal', later)
        suspend_account(self.user, '도배', reason=SuspensionReason.SPAM)

        self.complete()

        row = blocks()[ReturnBlockKind.EMAIL]
        self.assertEqual((row.reason, row.expires_at), ('illegal', later))

    def test_an_earlier_block_is_extended(self):
        block(ReturnBlockKind.EMAIL, email_key(EMAIL), 'spam', self.now + timedelta(days=10))
        suspend_account(self.user, '욕설', reason=SuspensionReason.ABUSE)

        self.complete()

        row = blocks()[ReturnBlockKind.EMAIL]
        self.assertEqual((row.reason, row.expires_at), ('abuse', self.now + timedelta(days=365)))

    def test_recording_counts_what_it_left(self):
        verify_identity(user=self.user, token=identity_token(PERSON))
        suspend_account(self.user, '도배', reason=SuspensionReason.SPAM)

        self.assertEqual(record_return_blocks(self.user, EMAIL, self.now), 2)
        other = make_user('player_02', 'two@example.com')
        self.assertEqual(record_return_blocks(other, 'two@example.com', self.now), 0)


@override_settings(BILLING_SECRET=SECRET)
class IdentityTests(APITestCase):
    """새 계정의 본인인증."""

    def setUp(self):
        self.user = make_user('player_02', 'new@example.com')
        authorize(self.client, self.user)

    def blocked_for(self, reason: str, *, expires_in: timedelta = timedelta(days=30)) -> None:
        block(ReturnBlockKind.IDENTITY, person_key(PERSON), reason, timezone.now() + expires_in)

    def test_a_spam_return_is_refused_and_the_account_stays(self):
        self.blocked_for('spam')

        response = post_identity(self.client, identity_token(PERSON))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'identity_blocked')
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        # 인증하지 않았다. 환영 크레딧도 없다
        self.assertFalse(IdentityVerification.objects.filter(user=self.user).exists())
        self.assertFalse(WelcomeCredit.objects.exists())
        [event] = SecurityEvent.objects.filter(kind=SecurityEventKind.RETURN_BLOCKED)
        self.assertEqual((event.user, event.note), (self.user, '본인인증 / spam'))

    def test_an_abuse_return_suspends_the_new_account(self):
        self.blocked_for('abuse')

        response = post_identity(self.client, identity_token(PERSON))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        [suspension] = Suspension.objects.filter(user=self.user)
        self.assertEqual((suspension.reason, suspension.note), ('abuse', RETURN_SUSPENSION_NOTE))
        self.assertFalse(IdentityVerification.objects.filter(user=self.user).exists())

    def test_every_reason_follows_its_rule(self):
        for reason, policy in POLICIES.items():
            with self.subTest(reason=reason):
                ReturnBlock.objects.all().delete()
                Suspension.objects.all().delete()
                User.objects.filter(pk=self.user.pk).update(is_active=True)
                self.blocked_for(reason)

                with self.assertRaises(IdentityBlockedError):
                    verify_identity(user=User.objects.get(pk=self.user.pk), token=identity_token(PERSON))

                self.user.refresh_from_db()
                self.assertEqual(self.user.is_active, policy.identity is IdentityRule.REFUSE)

    def test_an_expired_block_does_not_stop_anyone(self):
        self.blocked_for('illegal', expires_in=timedelta(seconds=-1))

        response = post_identity(self.client, identity_token(PERSON))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_another_person_is_not_stopped(self):
        self.blocked_for('illegal')

        response = post_identity(self.client, identity_token('person-2'))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class SignupTests(APITestCase):
    """가입 1단계."""

    def start(self, email: str = EMAIL):
        return self.client.post(SIGNUP_URL, {'email': email}, format='json')

    def test_a_blocked_email_gets_the_same_answer_and_no_code(self):
        block(ReturnBlockKind.EMAIL, email_key(EMAIL), 'spam', timezone.now() + timedelta(days=30))

        response = self.start(' Leaver@Example.com ')

        # 응답으로 막힌 주소인지 알 수 없다
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        # 발송 횟수만 센 줄이다. 맞힐 코드가 없다
        self.assertFalse(SignupCode.objects.exclude(code_hash='').exists())
        (message,) = mail.outbox
        self.assertEqual(message.to, [EMAIL])
        self.assertIn('가입할 수 없습니다', message.subject)
        # 정지의 사유는 적지 않는다
        self.assertNotIn('spam', message.body)
        [event] = SecurityEvent.objects.filter(kind=SecurityEventKind.RETURN_BLOCKED)
        self.assertEqual((event.user, event.note), (None, '가입'))

    def test_an_open_email_gets_a_code(self):
        block(ReturnBlockKind.EMAIL, email_key('other@example.com'), 'spam', timezone.now() + timedelta(days=30))
        block(ReturnBlockKind.EMAIL, email_key(EMAIL), 'spam', timezone.now() - timedelta(seconds=1))

        response = self.start()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(SignupCode.objects.exclude(code_hash='').exists())
        self.assertIn('인증 코드', mail.outbox[0].subject)

    def test_the_refusal_mail_counts_against_the_same_limit(self):
        # 가입 코드와 같은 발급 제한이다. 1분 안에 다시 불러도 메일은 한 통이다
        block(ReturnBlockKind.EMAIL, email_key(EMAIL), 'spam', timezone.now() + timedelta(days=30))

        self.start()
        self.start()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(SecurityEvent.objects.filter(kind=SecurityEventKind.RETURN_BLOCKED).count(), 1)


class CleanupTests(TestCase):
    def test_a_block_stops_when_cleanup_would_delete_it(self):
        # 막는 것과 지우는 것의 경계가 같다. 지울 때가 된 값은 막지 않는다
        now = timezone.now()
        row = block(ReturnBlockKind.EMAIL, 'a' * 64, 'spam', now)

        self.assertIsNone(active_block(ReturnBlockKind.EMAIL, row.key, now))
        self.assertEqual(active_block(ReturnBlockKind.EMAIL, row.key, now - timedelta(microseconds=1)), row)

    def test_expired_blocks_are_deleted(self):
        now = timezone.now()
        block(ReturnBlockKind.EMAIL, 'a' * 64, 'spam', now)
        block(ReturnBlockKind.EMAIL, 'b' * 64, 'spam', now + timedelta(seconds=1))

        self.assertEqual(delete_expired_blocks(now), 1)
        self.assertEqual([row.key for row in ReturnBlock.objects.all()], ['b' * 64])

    def test_the_hourly_digest_deletes_them(self):
        block(ReturnBlockKind.EMAIL, 'a' * 64, 'spam', timezone.now() - timedelta(days=1))
        output = StringIO()

        call_command('send_security_digest', stdout=output)

        self.assertIn('지운 재가입 막기 1건', output.getvalue())
        self.assertFalse(ReturnBlock.objects.exists())

    def test_the_operator_lifts_a_block_on_the_admin_screen(self):
        block_admin = admin.site._registry[ReturnBlock]

        self.assertFalse(block_admin.has_add_permission(None))
        self.assertFalse(block_admin.has_change_permission(None))
        self.assertTrue(block_admin.has_delete_permission(_superuser_request()))


def _superuser_request():
    """관리 화면의 권한을 묻는 요청. 지울 권한은 사용자의 권한으로 정해진다."""
    request = type('Request', (), {})()
    request.user = User(is_superuser=True, is_staff=True, is_active=True)
    return request
