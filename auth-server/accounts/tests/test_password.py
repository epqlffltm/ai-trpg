# auth-server/accounts/tests/test_password.py

"""
비밀번호 변경과 재설정을 검증한다.

변경은 로그인한 사람이, 재설정은 비밀번호를 잊어 로그인하지 못하는 사람이 쓴다.
"""

from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.email_codes import ISSUE_COOLDOWN, MAX_FAILED_ATTEMPTS, TOKEN_LIFETIME
from accounts.models import EmailCode, User
from accounts.tests.helpers import log_in, start_login

CHANGE_URL = reverse('accounts:password-change')
RESET_URL = reverse('accounts:password-reset')
RESET_CONFIRM_URL = reverse('accounts:password-reset-confirm')
REFRESH_URL = reverse('accounts:refresh')
ME_URL = reverse('accounts:me')

EMAIL = 'someone@example.com'
OLD_PASSWORD = 'correct-horse-battery'
NEW_PASSWORD = 'brand-new-staple-42'


def create_user(**overrides) -> User:
    fields = {
        'username': 'player_01',
        'email': EMAIL,
        'nickname': '플레이어',
        'password': OLD_PASSWORD,
        'email_verified_at': timezone.now(),
    }
    fields.update(overrides)
    return User.objects.create_user(**fields)


def reset_link_from(message) -> str:
    """재설정 메일의 본문에서 링크를 꺼낸다."""
    return next(line for line in message.body.splitlines() if line.startswith(settings.PASSWORD_RESET_URL))


def token_from(message) -> str:
    """재설정 링크의 # 뒤에서 토큰을 꺼낸다. 프론트의 재설정 화면이 하게 될 일이다."""
    fragment = urlsplit(reset_link_from(message)).fragment
    return parse_qs(fragment)['token'][0]


def after(elapsed: timedelta):
    """인증 코드 쪽의 시계를 elapsed 만큼 뒤로 옮긴다."""
    return patch('accounts.email_codes.timezone.now', return_value=timezone.now() + elapsed)


class PasswordChangeTests(APITestCase):
    def setUp(self):
        self.user = create_user()
        self.access_token = log_in(self.client, 'player_01', OLD_PASSWORD).data['access_token']
        mail.outbox.clear()

    def change(self, current_password: str = OLD_PASSWORD, new_password: str = NEW_PASSWORD, token: str | None = None):
        return self.client.post(
            CHANGE_URL,
            {'current_password': current_password, 'new_password': new_password},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {token or self.access_token}',
        )

    def get_me(self, access_token: str):
        return APIClient().get(ME_URL, HTTP_AUTHORIZATION=f'Bearer {access_token}')

    def test_changes_the_password(self):
        response = self.change()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_requires_login(self):
        response = self.client.post(
            CHANGE_URL,
            {'current_password': OLD_PASSWORD, 'new_password': NEW_PASSWORD},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_wrong_current_password(self):
        response = self.change(current_password='not-my-password')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('current_password', response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_rejects_weak_new_passwords(self):
        weak_passwords = [
            'short1!',          # 8자 미만
            '1234567890',       # 숫자만
            'password123',      # 흔한 비밀번호
            'player_01',        # 아이디와 같음
            OLD_PASSWORD,       # 현재 비밀번호와 같음
        ]
        for new_password in weak_passwords:
            with self.subTest(new_password=new_password):
                response = self.change(new_password=new_password)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('new_password', response.data)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_this_device_stays_logged_in(self):
        response = self.change()

        # 새 토큰을 받는다. 옛 access 토큰은 무효가 됐다
        self.assertEqual(self.get_me(response.data['access_token']).status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_me(self.access_token).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(REFRESH_URL).status_code, status.HTTP_200_OK)

    def test_other_devices_are_logged_out(self):
        other_device = APIClient()
        other_access_token = log_in(other_device, 'player_01', OLD_PASSWORD).data['access_token']

        self.change()

        self.assertEqual(self.get_me(other_access_token).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(other_device.post(REFRESH_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_failed_change_keeps_every_session(self):
        other_device = APIClient()
        log_in(other_device, 'player_01', OLD_PASSWORD)

        self.change(current_password='not-my-password')

        self.assertEqual(self.get_me(self.access_token).status_code, status.HTTP_200_OK)
        self.assertEqual(other_device.post(REFRESH_URL).status_code, status.HTTP_200_OK)

    def test_login_in_progress_cannot_be_completed_after_change(self):
        # 비밀번호를 아는 누군가가 로그인 1단계까지 가 있는 상태
        pending_ticket = start_login(APIClient(), 'player_01', OLD_PASSWORD).data['login_ticket']

        self.change()

        response = self.client.post(
            reverse('accounts:login-verify'),
            {'login_ticket': pending_ticket, 'code': '000000'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'login_ticket_invalid')

    def test_old_password_no_longer_logs_in(self):
        self.change()

        old = start_login(APIClient(), 'player_01', OLD_PASSWORD)
        new = start_login(APIClient(), 'player_01', NEW_PASSWORD)

        self.assertEqual(old.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(new.status_code, status.HTTP_202_ACCEPTED)

    def test_notifies_the_owner(self):
        self.change()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertIn('변경', mail.outbox[0].subject)
        self.assertNotIn(NEW_PASSWORD, mail.outbox[0].body)

    def test_failed_change_sends_no_notice(self):
        self.change(current_password='not-my-password')

        self.assertEqual(len(mail.outbox), 0)


class PasswordResetRequestTests(APITestCase):
    def setUp(self):
        self.user = create_user()

    def request_reset(self, email: str = EMAIL):
        return self.client.post(RESET_URL, {'email': email}, format='json')

    def test_sends_a_reset_link(self):
        response = self.request_reset()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertTrue(reset_link_from(mail.outbox[0]).startswith(settings.PASSWORD_RESET_URL + '#'))

    def test_link_keeps_the_token_out_of_the_query_string(self):
        self.request_reset()

        link = urlsplit(reset_link_from(mail.outbox[0]))
        # ? 뒤는 서버로 전송되어 접속 기록에 남는다. # 뒤는 전송되지 않는다
        self.assertEqual(link.query, '')
        self.assertEqual(parse_qs(link.fragment)['email'], [EMAIL])

    def test_token_is_long_and_not_stored_in_plain_text(self):
        self.request_reset()
        token = token_from(mail.outbox[0])

        self.assertGreaterEqual(len(token), 43)
        self.assertNotEqual(EmailCode.objects.get(user=self.user).code_hash, token)

    def test_mail_tells_the_username(self):
        self.request_reset()

        # 비밀번호를 잊은 사람은 아이디도 잊었을 수 있다
        self.assertIn('player_01', mail.outbox[0].body)

    def test_email_match_ignores_case(self):
        self.request_reset(email='SOMEONE@example.com')

        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_email_gets_the_same_response_and_no_mail(self):
        known = self.request_reset()
        mail.outbox.clear()

        unknown = self.request_reset(email='nobody@example.com')

        self.assertEqual(unknown.status_code, known.status_code)
        self.assertEqual(unknown.data, known.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_unverified_and_inactive_accounts_get_no_mail(self):
        create_user(username='pending_01', email='pending@example.com', nickname='미인증', email_verified_at=None)
        create_user(username='inactive_01', email='inactive@example.com', nickname='비활성', is_active=False)

        pending = self.request_reset(email='pending@example.com')
        inactive = self.request_reset(email='inactive@example.com')

        self.assertEqual(pending.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(inactive.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(len(mail.outbox), 0)

    def test_requests_are_rate_limited_without_changing_the_response(self):
        first = self.request_reset()
        second = self.request_reset()

        self.assertEqual(second.data, first.data)
        # 요청을 반복해 남의 메일함에 재설정 메일을 쏟아부을 수 없어야 한다
        self.assertEqual(len(mail.outbox), 1)

    def test_does_not_change_the_password_or_sessions(self):
        access_token = log_in(self.client, 'player_01', OLD_PASSWORD).data['access_token']

        self.request_reset()

        # 요청만으로는 아무것도 바뀌지 않는다. 남이 요청해도 주인은 영향을 받지 않는다
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))
        me = APIClient().get(ME_URL, HTTP_AUTHORIZATION=f'Bearer {access_token}')
        self.assertEqual(me.status_code, status.HTTP_200_OK)


class PasswordResetConfirmTests(APITestCase):
    def setUp(self):
        self.user = create_user()
        self.client.post(RESET_URL, {'email': EMAIL}, format='json')
        self.token = token_from(mail.outbox[0])
        mail.outbox.clear()

    def confirm(self, token: str | None = None, new_password: str = NEW_PASSWORD, email: str = EMAIL):
        return self.client.post(
            RESET_CONFIRM_URL,
            {'email': email, 'token': token or self.token, 'new_password': new_password},
            format='json',
        )

    def test_sets_the_new_password(self):
        response = self.confirm()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_does_not_log_the_user_in(self):
        response = self.confirm()

        self.assertNotIn('access_token', response.data)
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)

    def test_rejects_wrong_token(self):
        response = self.confirm(token='not-the-real-token')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_unknown_email_gets_the_same_response_as_a_wrong_token(self):
        wrong_token = self.confirm(token='not-the-real-token')
        unknown_email = self.confirm(email='nobody@example.com')

        self.assertEqual(unknown_email.status_code, wrong_token.status_code)
        self.assertEqual(unknown_email.data, wrong_token.data)

    def test_token_cannot_be_used_twice(self):
        self.confirm()

        response = self.confirm(new_password='another-new-staple-77')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_rejects_expired_token(self):
        with after(TOKEN_LIFETIME):
            response = self.confirm()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_token_outlives_a_login_code(self):
        # 링크를 열어 새 비밀번호를 정하는 데는 코드를 입력하는 것보다 시간이 든다
        with after(TOKEN_LIFETIME - timedelta(minutes=1)):
            response = self.confirm()

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_wrong_tokens_do_not_burn_the_real_one(self):
        # 이메일만 아는 제3자가 남의 재설정을 방해할 수 없어야 한다
        for _ in range(MAX_FAILED_ATTEMPTS + 1):
            self.confirm(token='not-the-real-token')

        response = self.confirm()

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_newer_link_retires_the_older_one(self):
        with after(ISSUE_COOLDOWN):
            self.client.post(RESET_URL, {'email': EMAIL}, format='json')
            newer_token = token_from(mail.outbox[-1])
            older = self.confirm(token=self.token)
            newer = self.confirm(token=newer_token)

        self.assertEqual(older.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(newer.status_code, status.HTTP_200_OK)

    def test_weak_password_is_rejected_and_the_token_stays_usable(self):
        weak = self.confirm(new_password='player_01')

        self.assertEqual(weak.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', weak.data)
        # 비밀번호를 고쳐 같은 링크로 다시 시도할 수 있어야 한다
        self.assertEqual(self.confirm().status_code, status.HTTP_200_OK)

    def test_weak_password_with_wrong_token_reveals_nothing(self):
        # 토큰이 틀리면 비밀번호 규칙을 검사한 결과도 알려 주지 않는다.
        # "이 계정의 아이디와 비슷하다" 는 답은 계정이 있다는 사실을 알려 준다
        response = self.confirm(token='not-the-real-token', new_password='player_01')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('new_password', response.data)

    def test_logs_out_every_device(self):
        device = APIClient()
        access_token = log_in(device, 'player_01', OLD_PASSWORD).data['access_token']

        self.confirm()

        me = APIClient().get(ME_URL, HTTP_AUTHORIZATION=f'Bearer {access_token}')
        self.assertEqual(me.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(device.post(REFRESH_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sessions_survive_when_saving_the_password_fails(self):
        device = APIClient()
        log_in(device, 'player_01', OLD_PASSWORD)

        # 세션을 끊는 단계가 실패하면 비밀번호 변경과 토큰 소비도 함께 취소되어야 한다
        with patch('accounts.services.revoke_all_sessions', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.confirm()

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))
        self.assertEqual(device.post(REFRESH_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(self.confirm().status_code, status.HTTP_200_OK)

    def test_can_log_in_with_the_new_password(self):
        self.confirm()

        old = start_login(APIClient(), 'player_01', OLD_PASSWORD)
        new = log_in(APIClient(), 'player_01', NEW_PASSWORD)

        self.assertEqual(old.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(new.status_code, status.HTTP_200_OK)

    def test_notifies_the_owner(self):
        self.confirm()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('변경', mail.outbox[0].subject)
        self.assertNotIn(NEW_PASSWORD, mail.outbox[0].body)
