# auth-server/accounts/tests/test_suspension.py

"""
계정 정지와 정지 풀기(#274)를 검증한다. 정지하면 로그인과 refresh 가 막히고, 이미 발급된 토큰이 끊기고,
끊긴 세션 목록에 실려 다른 서버에서도 막힌다.
"""

from io import StringIO

from django.contrib import admin
from django.core.management import CommandError, call_command
from rest_framework import status

from accounts.mail import build_security_digest_message
from accounts.models import SecurityEvent, SecurityEventKind, User
from accounts.session_revocations import sub_digest
from accounts.suspension import (
    MAX_NOTE_LENGTH,
    InvalidNoteError,
    UnknownAccountError,
    clean_note,
    find_account,
    restore_account,
    suspend_account,
)
from accounts.tests.helpers import start_login
from accounts.tests.test_refresh import PASSWORD, REFRESH_URL, RefreshTestCase
from accounts.tests.test_session_revocations import SessionRevocationsTestCase

NOTE = '결제 사기 신고 확인'


def events(kind: str) -> list[SecurityEvent]:
    return list(SecurityEvent.objects.filter(kind=kind))


class SuspendTests(SessionRevocationsTestCase):
    def test_suspending_blocks_the_account_and_cuts_its_sessions(self):
        access_token = self.login_response.data['access_token']

        self.assertTrue(suspend_account(self.user, NOTE))

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.token_version, 1)
        # 이미 발급된 토큰은 인증 서버에서 바로 거부된다
        self.assertEqual(self.get_me(access_token).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(REFRESH_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_suspended_accounts_cannot_log_in(self):
        suspend_account(self.user, NOTE)

        response = start_login(self.client_class(), 'player_01', PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_other_servers_are_told(self):
        suspend_account(self.user, NOTE)

        self.assertEqual(self.entry_for(self.user), {'sub_sha256': sub_digest(str(self.user.public_id)), 'min_ver': 1})

    def test_the_reason_is_kept_as_a_security_event(self):
        suspend_account(self.user, NOTE)

        [event] = events(SecurityEventKind.ACCOUNT_SUSPENDED)
        self.assertEqual((event.user, event.note), (self.user, NOTE))

    def test_suspending_twice_changes_nothing(self):
        suspend_account(self.user, NOTE)

        self.assertFalse(suspend_account(self.user, NOTE))

        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 1)
        self.assertEqual(len(events(SecurityEventKind.ACCOUNT_SUSPENDED)), 1)


class RestoreTests(RefreshTestCase):
    def test_restoring_lets_the_user_log_in_again(self):
        suspend_account(self.user, NOTE)

        self.assertTrue(restore_account(self.user, '신고 오인'))

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(start_login(self.client_class(), 'player_01', PASSWORD).status_code, status.HTTP_202_ACCEPTED)

    def test_restoring_does_not_bring_back_the_old_sessions(self):
        suspend_account(self.user, NOTE)
        restore_account(self.user, '신고 오인')

        self.assertEqual(self.client.post(REFRESH_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, 1)

    def test_restoring_an_active_account_changes_nothing(self):
        self.assertFalse(restore_account(self.user, '신고 오인'))
        self.assertEqual(events(SecurityEventKind.ACCOUNT_RESTORED), [])

    def test_the_reason_is_kept(self):
        suspend_account(self.user, NOTE)
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


class CommandTests(RefreshTestCase):
    def run_command(self, *args: str) -> str:
        out = StringIO()
        call_command(*args, stdout=out)
        return out.getvalue()

    def test_suspend_and_restore_from_the_command_line(self):
        said = self.run_command('suspend_account', 'player_01', '--reason', NOTE)
        self.assertIn('정지했습니다', said)
        self.assertIn('이미', self.run_command('suspend_account', 'player_01', '--reason', NOTE))

        said = self.run_command('restore_account', 'player_01', '--reason', '신고 오인')
        self.assertIn('풀었습니다', said)
        self.assertIn(
            '정지된 계정이 아닙니다', self.run_command('restore_account', 'player_01', '--reason', '신고 오인')
        )

    def test_the_command_refuses_bad_input(self):
        for command in ('suspend_account', 'restore_account'):
            with self.subTest(command=command):
                with self.assertRaisesMessage(CommandError, '그런 아이디의 계정이 없습니다'):
                    self.run_command(command, 'nobody', '--reason', NOTE)
                with self.assertRaisesMessage(CommandError, '사유'):
                    self.run_command(command, 'player_01', '--reason', '  ')
                with self.assertRaises(CommandError):
                    self.run_command(command, 'player_01')

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)


class DigestTests(RefreshTestCase):
    def test_the_digest_mail_carries_the_reason(self):
        suspend_account(self.user, NOTE)

        _, body = build_security_digest_message(events=events(SecurityEventKind.ACCOUNT_SUSPENDED))

        self.assertIn('계정: 정지', body)
        self.assertIn(f'사유 {NOTE}', body)


class AdminTests(RefreshTestCase):
    def test_the_admin_screen_cannot_turn_the_account_off(self):
        # 화면에서 끄면 세션 버전이 오르지 않는다. 정지는 명령으로 한다
        user_admin = admin.site._registry[User]

        self.assertIn('is_active', user_admin.readonly_fields)
