# auth-server/accounts/tests/test_refresh.py

"""
refresh 토큰의 발급, 회전, 폐기, 세션 버전을 검증한다.
"""

from datetime import timedelta

import jwt
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts.cookies import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from accounts.models import User
from accounts.tests.helpers import BrowserClient, log_in
from accounts.tokens import RefreshToken, issue_token_pair, revoke_all_sessions

REFRESH_URL = reverse('accounts:refresh')
LOGOUT_URL = reverse('accounts:logout')
LOGOUT_ALL_URL = reverse('accounts:logout-all')
ME_URL = reverse('accounts:me')

PASSWORD = 'correct-horse-battery'


def create_user(**overrides) -> User:
    fields = {
        'username': 'player_01',
        'email': 'someone@example.com',
        'nickname': '플레이어',
        'password': PASSWORD,
        # 이메일 인증을 끝낸 계정이어야 로그인할 수 있다
        'email_verified_at': timezone.now(),
    }
    fields.update(overrides)
    return User.objects.create_user(**fields)


class RefreshTestCase(APITestCase):
    """로그인해서 refresh 쿠키를 가진 상태에서 시작한다."""

    client_class = BrowserClient

    def setUp(self):
        self.user = create_user()
        self.login_response = self.login(self.client)

    def login(self, client: APIClient):
        return log_in(client, 'player_01', PASSWORD)

    def refresh_cookie_value(self, client: APIClient | None = None) -> str:
        return (client or self.client).cookies[REFRESH_COOKIE_NAME].value

    def client_with_refresh_token(self, refresh_token: str) -> APIClient:
        """주어진 refresh 토큰을 쿠키로 가진 새 클라이언트. 다른 기기나 공격자를 흉내 낸다."""
        client = BrowserClient()
        client.cookies[REFRESH_COOKIE_NAME] = refresh_token
        return client

    def get_me(self, access_token: str):
        # 쿠키가 없는 새 클라이언트로 요청한다. access 토큰만으로 인증되는지 본다
        return BrowserClient().get(ME_URL, HTTP_AUTHORIZATION=f'Bearer {access_token}')


class RefreshCookieTests(RefreshTestCase):
    def test_login_sets_refresh_cookie(self):
        cookie = self.login_response.cookies[REFRESH_COOKIE_NAME]

        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')
        self.assertEqual(cookie['path'], REFRESH_COOKIE_PATH)
        self.assertEqual(cookie['max-age'], 14 * 24 * 60 * 60)

    def test_refresh_token_is_not_in_response_body(self):
        self.assertNotIn('refresh_token', self.login_response.data)
        self.assertNotIn(self.refresh_cookie_value(), str(self.login_response.data))

    def test_refresh_token_text_is_not_stored(self):
        issued = OutstandingToken.objects.get(user=self.user)

        # DB 를 읽을 수 있는 사람이 남의 세션을 쓸 수 없어야 한다
        self.assertEqual(issued.token, '')


class RefreshRotationTests(RefreshTestCase):
    def test_returns_new_access_token(self):
        response = self.client.post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_me(response.data['access_token']).status_code, status.HTTP_200_OK)

    def test_replaces_refresh_token(self):
        old_refresh_token = self.refresh_cookie_value()

        self.client.post(REFRESH_URL)

        self.assertNotEqual(self.refresh_cookie_value(), old_refresh_token)

    def test_new_refresh_token_works(self):
        self.client.post(REFRESH_URL)

        response = self.client.post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_new_access_token_carries_the_current_nickname(self):
        # 로그인한 뒤에 이름이 바뀌었다. 갱신하면 DB 의 지금 이름이 실린다
        User.objects.filter(pk=self.user.pk).update(nickname='새이름')

        response = self.client.post(REFRESH_URL)

        claims = jwt.decode(response.data['access_token'], options={'verify_signature': False})
        self.assertEqual(claims['nickname'], '새이름')

    def test_old_refresh_token_is_revoked(self):
        self.client.post(REFRESH_URL)

        self.assertEqual(BlacklistedToken.objects.count(), 1)

    def test_requires_cookie(self):
        response = BrowserClient().post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_garbage(self):
        response = self.client_with_refresh_token('not-a-token').post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_access_token_in_refresh_cookie(self):
        access_token = self.login_response.data['access_token']

        response = self.client_with_refresh_token(access_token).post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_expired_refresh_token(self):
        token = RefreshToken(self.refresh_cookie_value())
        token.set_exp(lifetime=-timedelta(minutes=1))

        response = self.client_with_refresh_token(str(token)).post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_deactivated_user(self):
        self.user.is_active = False
        self.user.save()

        response = self.client.post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_failed_refresh_clears_cookie(self):
        response = self.client_with_refresh_token('not-a-token').post(REFRESH_URL)

        # 쓸 수 없는 쿠키를 브라우저가 계속 들고 다니지 않게 한다
        self.assertEqual(response.cookies[REFRESH_COOKIE_NAME].value, '')


class RefreshReuseTests(RefreshTestCase):
    """이미 쓴 refresh 토큰이 다시 들어오는 경우. 토큰이 탈취됐다는 신호다."""

    def setUp(self):
        super().setUp()
        self.stolen_refresh_token = self.refresh_cookie_value()
        # 정상 사용자가 먼저 갱신한다. 훔친 토큰은 이 시점에 폐기된다
        self.refreshed = self.client.post(REFRESH_URL)

    def test_reused_token_is_rejected(self):
        response = self.client_with_refresh_token(self.stolen_refresh_token).post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reuse_revokes_the_legitimate_session_too(self):
        self.client_with_refresh_token(self.stolen_refresh_token).post(REFRESH_URL)

        # 누가 진짜인지 알 수 없으므로 양쪽 다 끊는다
        response = self.client.post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reuse_revokes_access_tokens(self):
        access_token = self.refreshed.data['access_token']

        self.client_with_refresh_token(self.stolen_refresh_token).post(REFRESH_URL)

        self.assertEqual(self.get_me(access_token).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_log_in_again_after_reuse(self):
        self.client_with_refresh_token(self.stolen_refresh_token).post(REFRESH_URL)

        new_client = BrowserClient()
        self.login(new_client)

        self.assertEqual(new_client.post(REFRESH_URL).status_code, status.HTTP_200_OK)

    def test_reusing_the_same_old_token_again_does_not_cut_the_new_session(self):
        # #272: 재사용을 한 번 감지해 모든 세션을 끊었다. 그 뒤에 새로 로그인한 세션은
        # 같은 옛 토큰을 다시 보내도 끊기지 않는다. 옛 토큰이 남을 로그아웃시키는 수단이 되지 않는다
        self.client_with_refresh_token(self.stolen_refresh_token).post(REFRESH_URL)
        new_client = BrowserClient()
        access_token = self.login(new_client).data['access_token']
        version = User.objects.get(pk=self.user.pk).token_version

        # 401 은 쿠키를 지운다. 옛 토큰을 가진 사람은 쿠키를 다시 넣어 보낸다
        replayed = [
            self.client_with_refresh_token(self.stolen_refresh_token).post(REFRESH_URL).status_code for _ in range(3)
        ]

        self.assertEqual(replayed, [status.HTTP_401_UNAUTHORIZED] * 3)
        self.assertEqual(User.objects.get(pk=self.user.pk).token_version, version)
        self.assertEqual(self.get_me(access_token).status_code, status.HTTP_200_OK)
        self.assertEqual(new_client.post(REFRESH_URL).status_code, status.HTTP_200_OK)

    def test_reuse_of_a_current_token_still_cuts_every_session(self):
        # 지금 세대의 재사용은 여전히 탈취의 신호다. 새 세션에서 갱신한 뒤 그 앞의 토큰을 다시 보낸다
        self.client_with_refresh_token(self.stolen_refresh_token).post(REFRESH_URL)
        new_client = BrowserClient()
        self.login(new_client)
        current_but_used = self.refresh_cookie_value(new_client)
        new_client.post(REFRESH_URL)

        response = self.client_with_refresh_token(current_but_used).post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(new_client.post(REFRESH_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_token_from_before_logout_all_is_refused_without_cutting_again(self):
        # 모든 기기 로그아웃으로 버전이 올랐다. 그 전의 폐기된 토큰도 지난 세대라 거부만 한다
        revoke_all_sessions(self.user)
        new_client = BrowserClient()
        self.login(new_client)
        version = User.objects.get(pk=self.user.pk).token_version

        response = self.client_with_refresh_token(self.stolen_refresh_token).post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(User.objects.get(pk=self.user.pk).token_version, version)
        self.assertEqual(new_client.post(REFRESH_URL).status_code, status.HTTP_200_OK)


class LogoutTests(RefreshTestCase):
    def test_returns_204_and_clears_cookie(self):
        response = self.client.post(LOGOUT_URL)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.cookies[REFRESH_COOKIE_NAME].value, '')

    def test_revokes_refresh_token(self):
        refresh_token = self.refresh_cookie_value()

        self.client.post(LOGOUT_URL)

        response = self.client_with_refresh_token(refresh_token).post(REFRESH_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_does_not_end_other_sessions(self):
        other_device = BrowserClient()
        self.login(other_device)

        self.client.post(LOGOUT_URL)

        self.assertEqual(other_device.post(REFRESH_URL).status_code, status.HTTP_200_OK)

    def test_reusing_logged_out_token_ends_every_session(self):
        # 로그아웃한 토큰이 다시 들어온 것도 "폐기된 토큰의 재사용" 이다.
        # 이 경우에도 모든 세션을 끊는다. 훔친 토큰일 수 있기 때문이다
        refresh_token = self.refresh_cookie_value()
        other_device = BrowserClient()
        self.login(other_device)
        self.client.post(LOGOUT_URL)

        self.client_with_refresh_token(refresh_token).post(REFRESH_URL)

        self.assertEqual(other_device.post(REFRESH_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_succeeds_without_cookie(self):
        response = BrowserClient().post(LOGOUT_URL)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_succeeds_with_invalid_cookie(self):
        response = self.client_with_refresh_token('not-a-token').post(LOGOUT_URL)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class LogoutAllTests(RefreshTestCase):
    def logout_all(self, access_token: str):
        return self.client.post(LOGOUT_ALL_URL, HTTP_AUTHORIZATION=f'Bearer {access_token}')

    def test_requires_access_token(self):
        response = self.client.post(LOGOUT_ALL_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_ends_every_session(self):
        other_device = BrowserClient()
        self.login(other_device)

        response = self.logout_all(self.login_response.data['access_token'])

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(other_device.post(REFRESH_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_revokes_access_tokens(self):
        access_token = self.login_response.data['access_token']

        self.logout_all(access_token)

        self.assertEqual(self.get_me(access_token).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_does_not_affect_other_users(self):
        other_user = create_user(
            username='player_02',
            email='another@example.com',
            nickname='다른사람',
        )
        other_access_token = issue_token_pair(other_user).access

        self.logout_all(self.login_response.data['access_token'])

        self.assertEqual(self.get_me(other_access_token).status_code, status.HTTP_200_OK)


class SessionVersionTests(APITestCase):
    def test_revoke_all_sessions_increments_version(self):
        user = create_user()

        revoke_all_sessions(user)
        revoke_all_sessions(user)

        user.refresh_from_db()
        self.assertEqual(user.token_version, 2)

    def test_tokens_carry_the_version(self):
        user = create_user()
        revoke_all_sessions(user)

        token_pair = issue_token_pair(user)

        self.assertEqual(RefreshToken(token_pair.refresh)['ver'], 1)
