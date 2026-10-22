# auth-server/accounts/tests/test_suspension.py

"""
계정 정지와 정지 풀기(#274)를 검증한다. 정지하면 로그인과 refresh 가 막히고, 이미 발급된 토큰이 끊기고,
끊긴 세션 목록에 실려 다른 서버에서도 막힌다.
정지의 기록(#634)에 사유의 종류와 사유, 정지한 시각과 푼 시각이 남는다. 이미 정지된 계정은 마이그레이션이 적는다.
"""

import importlib
from io import StringIO

from django.apps import apps
from django.contrib import admin
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status

from accounts.erasure import blank_account
from accounts.mail import build_security_digest_message
from accounts.models import SecurityEvent, SecurityEventKind, Suspension, SuspensionReason, User
from accounts.session_revocations import sub_digest
from accounts.suspension import (
    MAX_NOTE_LENGTH,
    InvalidNoteError,
    UnknownAccountError,
    UnknownReasonError,
    clean_note,
    clean_reason,
    find_account,
    restore_account,
    suspend_account,
)
from accounts.tests.helpers import start_login
from accounts.tests.test_refresh import PASSWORD, REFRESH_URL, RefreshTestCase
from accounts.tests.test_session_revocations import SessionRevocationsTestCase

NOTE = '결제 사기 신고 확인'
REASON = SuspensionReason.FRAUD


def events(kind: str) -> list[SecurityEvent]:
    return list(SecurityEvent.objects.filter(kind=kind))


def records(user: User) -> list[Suspension]:
    """그 계정의 정지의 기록. 처음 것부터."""
    return list(Suspension.objects.filter(user=user).order_by('suspended_at', 'pk'))


class SuspendTests(SessionRevocationsTestCase):
    def test_suspending_blocks_the_account_and_cuts_its_sessions(self):
        access_token = self.login_response.data['access_token']

        self.assertTrue(suspend_account(self.user, NOTE, reason=REASON))

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.token_version, 1)
        # 이미 발급된 토큰은 인증 서버에서 바로 거부된다
        self.assertEqual(self.get_me(access_token).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(REFRESH_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_suspended_accounts_cannot_log_in(self):
        suspend_account(self.user, NOTE, reason=REASON)

        response = start_login(self.client_class(), 'player_01', PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_other_servers_are_told(self):
        suspend_account(self.user, NOTE, reason=REASON)

        self.assertEqual(self.entry_for(self.user), {'sub_sha256': sub_digest(str(self.user.public_id)), 'min_ver': 1})

    def test_the_reason_is_kept_as_a_security_event(self):
        suspend_account(self.user, NOTE, reason=REASON)

        [event] = events(SecurityEventKind.ACCOUNT_SUSPENDED)
        self.assertEqual((event.user, event.note), (self.user, NOTE))

    def test_the_suspension_is_recorded_with_its_kind(self):
        before = timezone.now()

        suspend_account(self.user, NOTE, reason=REASON)

        [record] = records(self.user)
        self.assertEqual((record.reason, record.note, record.restored_at), (REASON, NOTE, None))
        self.assertGreaterEqual(record.suspended_at, before)

    def test_suspending_twice_changes_nothing(self):
        suspend_account(self.user, NOTE, reason=REASON)

        self.assertFalse(suspend_account(self.user, NOTE, reason=SuspensionReason.SPAM))

        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 1)
        self.assertEqual(len(events(SecurityEventKind.ACCOUNT_SUSPENDED)), 1)
        # 처음의 사유가 그대로다
        self.assertEqual([record.reason for record in records(self.user)], [REASON])

    def test_an_account_has_at_most_one_open_suspension(self):
        # 정지와 풀기는 계정의 줄을 잠그고 한다. 그 밖의 길로 둘째 줄을 적어도 DB 가 막는다
        suspend_account(self.user, NOTE, reason=REASON)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Suspension.objects.create(user=self.user, reason=REASON, note=NOTE, suspended_at=timezone.now())


class RestoreTests(RefreshTestCase):
    def test_restoring_lets_the_user_log_in_again(self):
        suspend_account(self.user, NOTE, reason=REASON)

        self.assertTrue(restore_account(self.user, '신고 오인'))

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(start_login(self.client_class(), 'player_01', PASSWORD).status_code, status.HTTP_202_ACCEPTED)

    def test_restoring_does_not_bring_back_the_old_sessions(self):
        suspend_account(self.user, NOTE, reason=REASON)
        restore_account(self.user, '신고 오인')

        self.assertEqual(self.client.post(REFRESH_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 1)

    def test_restoring_an_active_account_changes_nothing(self):
        self.assertFalse(restore_account(self.user, '신고 오인'))
        self.assertEqual(events(SecurityEventKind.ACCOUNT_RESTORED), [])
        self.assertEqual(records(self.user), [])

    def test_restoring_closes_the_record(self):
        suspend_account(self.user, NOTE, reason=REASON)
        before = timezone.now()

        restore_account(self.user, '신고 오인')

        [record] = records(self.user)
        self.assertEqual((record.reason, record.note, record.restore_note), (REASON, NOTE, '신고 오인'))
        self.assertGreaterEqual(record.restored_at, before)

    def test_a_second_suspension_is_a_new_record(self):
        suspend_account(self.user, NOTE, reason=REASON)
        restore_account(self.user, '신고 오인')

        suspend_account(self.user, '도배', reason=SuspensionReason.SPAM)

        first, second = records(self.user)
        self.assertIsNotNone(first.restored_at)
        self.assertEqual((second.reason, second.note, second.restored_at), (SuspensionReason.SPAM, '도배', None))

    def test_restoring_again_leaves_the_earlier_record_alone(self):
        suspend_account(self.user, NOTE, reason=REASON)
        restore_account(self.user, '신고 오인')
        suspend_account(self.user, '도배', reason=SuspensionReason.SPAM)

        restore_account(self.user, '기간이 끝남')

        first, second = records(self.user)
        self.assertEqual((first.restore_note, second.restore_note), ('신고 오인', '기간이 끝남'))
        self.assertLess(first.restored_at, second.restored_at)

    def test_the_reason_is_kept(self):
        suspend_account(self.user, NOTE, reason=REASON)
        restore_account(self.user, '신고 오인')

        [event] = events(SecurityEventKind.ACCOUNT_RESTORED)
        self.assertEqual((event.user, event.note), (self.user, '신고 오인'))


class NoteAndLookupTests(RefreshTestCase):
    def test_the_note_is_trimmed(self):
        self.assertEqual(clean_note(f'  {NOTE}  '), NOTE)

    def test_an_empty_or_long_note_is_refused(self):
        for note in ('', '   ', 'x' * (MAX_NOTE_LENGTH + 1)):
            with self.subTest(length=len(note)), self.assertRaises(InvalidNoteError):
                clean_note(note)

    def test_the_username_is_matched_like_at_login(self):
        self.assertEqual(find_account(' Player_01 '), self.user)

    def test_an_unknown_username_is_refused(self):
        with self.assertRaises(UnknownAccountError):
            find_account('nobody')

    def test_the_reason_kind_is_matched_loosely(self):
        self.assertEqual(clean_reason(' Fraud '), SuspensionReason.FRAUD)

    def test_an_unknown_reason_kind_is_refused(self):
        for reason in ('', 'hacking', '사기'):
            with self.subTest(reason=reason), self.assertRaises(UnknownReasonError):
                clean_reason(reason)


class CommandTests(RefreshTestCase):
    def run_command(self, *args: str) -> str:
        out = StringIO()
        call_command(*args, stdout=out)
        return out.getvalue()

    def test_suspend_and_restore_from_the_command_line(self):
        said = self.run_command('suspend_account', 'player_01', '--kind', 'fraud', '--reason', NOTE)
        self.assertIn('정지했습니다', said)
        self.assertIn('이미', self.run_command('suspend_account', 'player_01', '--kind', 'fraud', '--reason', NOTE))
        self.assertEqual([record.reason for record in records(self.user)], [SuspensionReason.FRAUD])

        said = self.run_command('restore_account', 'player_01', '--reason', '신고 오인')
        self.assertIn('풀었습니다', said)
        self.assertIn(
            '정지된 계정이 아닙니다', self.run_command('restore_account', 'player_01', '--reason', '신고 오인')
        )

    def test_the_command_refuses_bad_input(self):
        commands = {'suspend_account': ('--kind', 'fraud'), 'restore_account': ()}
        for command, kind in commands.items():
            with self.subTest(command=command):
                with self.assertRaisesMessage(CommandError, '그런 아이디의 계정이 없습니다'):
                    self.run_command(command, 'nobody', *kind, '--reason', NOTE)
                with self.assertRaisesMessage(CommandError, '사유'):
                    self.run_command(command, 'player_01', *kind, '--reason', '  ')
                with self.assertRaises(CommandError):
                    self.run_command(command, 'player_01', *kind)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_suspending_needs_a_known_kind(self):
        with self.assertRaisesMessage(CommandError, 'spam, abuse, fraud, illegal, other'):
            self.run_command('suspend_account', 'player_01', '--kind', 'hacking', '--reason', NOTE)
        # 사유의 종류를 빠뜨리면 argparse 가 막는다
        with self.assertRaises(CommandError):
            self.run_command('suspend_account', 'player_01', '--reason', NOTE)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(records(self.user), [])


class DigestTests(RefreshTestCase):
    def test_the_digest_mail_carries_the_reason(self):
        suspend_account(self.user, NOTE, reason=REASON)

        _, body = build_security_digest_message(events=events(SecurityEventKind.ACCOUNT_SUSPENDED))

        self.assertIn('계정: 정지', body)
        self.assertIn(f'사유 {NOTE}', body)


class AdminTests(RefreshTestCase):
    def test_the_admin_screen_cannot_turn_the_account_off(self):
        # 화면에서 끄면 세션 버전이 오르지 않는다. 정지는 명령으로 한다
        user_admin = admin.site._registry[User]

        self.assertIn('is_active', user_admin.readonly_fields)

    def test_the_admin_screen_only_reads_suspensions(self):
        # 화면에서 고치면 계정이 막혔는지(is_active)와 기록이 어긋난다
        suspension_admin = admin.site._registry[Suspension]

        self.assertFalse(suspension_admin.has_add_permission(None))
        self.assertFalse(suspension_admin.has_change_permission(None))
        self.assertFalse(suspension_admin.has_delete_permission(None))


class BackfillTests(RefreshTestCase):
    """마이그레이션 0025 가 이미 정지된 계정에 기록을 적는다."""

    def backfill(self) -> None:
        migration = importlib.import_module('accounts.migrations.0025_suspensions')
        migration.record_existing_suspensions(apps, None)

    def test_an_account_suspended_before_the_records_gets_one(self):
        revoked = timezone.now()
        User.objects.filter(pk=self.user.pk).update(is_active=False, sessions_revoked_at=revoked)

        self.backfill()

        [record] = records(self.user)
        self.assertEqual((record.reason, record.restored_at, record.suspended_at), ('other', None, revoked))

    def test_active_and_emptied_accounts_get_none(self):
        emptied = User.objects.create_user(
            username='player_02', email='two@example.com', nickname='둘', password=PASSWORD
        )
        blank_account(emptied)

        self.backfill()

        self.assertEqual(list(Suspension.objects.all()), [])
