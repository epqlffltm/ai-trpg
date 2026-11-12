# auth-server/accounts/tests/test_app_tokens.py

"""
앱의 토큰 길(#429, accounts/app_views.py)을 검증한다.

refresh 토큰을 본문으로 주고받고, 쿠키는 쓰지 않는다. 브라우저의 요청은 거절한다.
앱에 준 토큰은 앱의 길로만, 웹에 준 토큰은 웹의 길로만 갱신된다.
"""

from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.models import IssuedTokenClient, TokenClient, User
from accounts.tests.helpers import BrowserClient, code_from, log_in, start_login

APP_LOGIN_VERIFY_URL = reverse('accounts:app-login-verify')
APP_REFRESH_URL = reverse('accounts:app-refresh')
APP_LOGOUT_URL = reverse('accounts:app-logout')
APP_PASSWORD_CHANGE_URL = reverse('accounts:app-password-change')
REFRESH_URL = reverse('accounts:refresh')
ME_URL = reverse('accounts:me')

PASSWORD = 'correct-horse-battery'
NEW_PASSWORD = 'another-horse-battery'


def create_user() -> User:
    return User.objects.create_user(
        username='player_01',
        email='someone@example.com',
        nickname='플레이어',
        password=PASSWORD,
        email_verified_at=timezone.now(),
    )


def app_log_in(client: APIClient, **headers):
    """앱처럼(Origin 없이) 로그인의 두 단계를 거친다. 1단계는 웹과 같은 길이다."""
    started = start_login(client, 'player_01', PASSWORD)
    assert started.status_code == status.HTTP_202_ACCEPTED, started.data
    return client.post(
        APP_LOGIN_VERIFY_URL,
        {'login_ticket': started.data['login_ticket'], 'code': code_from(mail.outbox[-1])},
        format='json',
        **headers,
    )


def client_of_token(raw_jti: str) -> str | None:
    return IssuedTokenClient.objects.filter(token__jti=raw_jti).values_list('client', flat=True).first()


class AppTokenTestCase(APITestCase):
    """앱의 네이티브 쪽처럼 Origin 을 붙이지 않는 클라이언트로 시작한다."""

    def setUp(self):
        self.user = create_user()

    def app_refresh(self, refresh_token: str, **headers):
        return APIClient().post(APP_REFRESH_URL, {'refresh_token': refresh_token}, format='json', **headers)

    def web_refresh_with(self, refresh_token: str):
        client = BrowserClient()
        client.cookies[REFRESH_COOKIE_NAME] = refresh_token
        return client.post(REFRESH_URL)


class AppLoginTests(AppTokenTestCase):
    def test_gives_refresh_token_in_body_without_cookie(self):
        response = app_log_in(self.client)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['refresh_token'])
        self.assertEqual(response.data['refresh_expires_in'], 14 * 24 * 60 * 60)
        self.assertEqual(response.data['token_type'], 'Bearer')
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)

    def test_access_token_works(self):
        access = app_log_in(self.client).data['access_token']

        response = APIClient().get(ME_URL, HTTP_AUTHORIZATION=f'Bearer {access}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_records_token_as_app(self):
        app_log_in(self.client)

        self.assertEqual(IssuedTokenClient.objects.get().client, TokenClient.APP)

    def test_web_login_records_token_as_web(self):
        log_in(BrowserClient(), 'player_01', PASSWORD)

        self.assertEqual(IssuedTokenClient.objects.get().client, TokenClient.WEB)

    def test_refuses_request_with_origin(self):
        response = app_log_in(self.client, HTTP_ORIGIN='https://example.com')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'browser_not_allowed')
        self.assertFalse(OutstandingToken.objects.exists())

    def test_refuses_null_origin(self):
        response = app_log_in(self.client, HTTP_ORIGIN='null')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_refuses_request_with_sec_fetch_site(self):
        response = app_log_in(self.client, HTTP_SEC_FETCH_SITE='same-origin')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'browser_not_allowed')

    def test_wrong_code_is_refused_like_web(self):
        started = start_login(self.client, 'player_01', PASSWORD)
        code = code_from(mail.outbox[-1])
        wrong = '000000' if code != '000000' else '111111'

        response = self.client.post(
            APP_LOGIN_VERIFY_URL, {'login_ticket': started.data['login_ticket'], 'code': wrong}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(OutstandingToken.objects.exists())


class AppRefreshTests(AppTokenTestCase):
    def setUp(self):
        super().setUp()
        self.refresh_token = app_log_in(self.client).data['refresh_token']

    def test_rotates_refresh_token(self):
        response = self.app_refresh(self.refresh_token)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['refresh_token'], self.refresh_token)
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)
        self.assertEqual(IssuedTokenClient.objects.filter(client=TokenClient.APP).count(), 2)

    def test_new_token_keeps_working(self):
        rotated = self.app_refresh(self.refresh_token).data['refresh_token']

        self.assertEqual(self.app_refresh(rotated).status_code, status.HTTP_200_OK)

    def test_reused_token_revokes_all_sessions(self):
        rotated = self.app_refresh(self.refresh_token).data['refresh_token']
        # 바꿔 받은 토큰도 쓴다. 쓰기 전이면 답을 잃은 것으로 보고 다시 준다(test_refresh_rotation.py)
        latest = self.app_refresh(rotated).data['refresh_token']

        reused = self.app_refresh(self.refresh_token)

        self.assertEqual(reused.status_code, status.HTTP_401_UNAUTHORIZED)
        # 탈취로 보고 모든 세션을 끊었다. 정상 사용자의 새 토큰도 끊긴다
        self.assertEqual(self.app_refresh(latest).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refuses_browser_request(self):
        response = self.app_refresh(self.refresh_token, HTTP_ORIGIN='https://example.com')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        # 거절만 하고 토큰은 그대로 쓸 수 있다
        self.assertEqual(self.app_refresh(self.refresh_token).status_code, status.HTTP_200_OK)

    def test_refuses_forged_token(self):
        response = self.app_refresh('not-a-token')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_requires_refresh_token(self):
        response = APIClient().post(APP_REFRESH_URL, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_app_token_is_refused_on_web_refresh(self):
        response = self.web_refresh_with(self.refresh_token)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        # 다른 곳의 길에서 거절한 것은 폐기도, 탈취로 보는 것도 아니다
        self.assertEqual(self.app_refresh(self.refresh_token).status_code, status.HTTP_200_OK)


class WebTokenOnAppTests(AppTokenTestCase):
    def setUp(self):
        super().setUp()
        self.browser = BrowserClient()
        log_in(self.browser, 'player_01', PASSWORD)
        self.web_token = self.browser.cookies[REFRESH_COOKIE_NAME].value

    def test_web_token_is_refused_on_app_refresh(self):
        response = self.app_refresh(self.web_token)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.browser.post(REFRESH_URL).status_code, status.HTTP_200_OK)

    def test_web_token_is_not_revoked_by_app_logout(self):
        response = APIClient().post(APP_LOGOUT_URL, {'refresh_token': self.web_token}, format='json')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.browser.post(REFRESH_URL).status_code, status.HTTP_200_OK)

    def test_token_without_record_is_web(self):
        # 이 표를 만들기 전에 발급된 토큰을 흉내 낸다
        IssuedTokenClient.objects.all().delete()

        self.assertEqual(self.browser.post(REFRESH_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(self.app_refresh(self.browser.cookies[REFRESH_COOKIE_NAME].value).status_code, 401)


class AppLogoutTests(AppTokenTestCase):
    def setUp(self):
        super().setUp()
        self.refresh_token = app_log_in(self.client).data['refresh_token']

    def test_revokes_token(self):
        response = APIClient().post(APP_LOGOUT_URL, {'refresh_token': self.refresh_token}, format='json')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.app_refresh(self.refresh_token).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_succeeds_without_token(self):
        response = APIClient().post(APP_LOGOUT_URL, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_succeeds_with_unusable_token(self):
        response = APIClient().post(APP_LOGOUT_URL, {'refresh_token': 'not-a-token'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_refuses_browser_request(self):
        response = APIClient().post(
            APP_LOGOUT_URL, {'refresh_token': self.refresh_token}, format='json', HTTP_ORIGIN='https://example.com'
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.app_refresh(self.refresh_token).status_code, status.HTTP_200_OK)


class AppPasswordChangeTests(AppTokenTestCase):
    def setUp(self):
        super().setUp()
        logged_in = app_log_in(self.client).data
        self.refresh_token = logged_in['refresh_token']
        self.access_token = logged_in['access_token']

    def change(self, **headers):
        return APIClient().post(
            APP_PASSWORD_CHANGE_URL,
            {'current_password': PASSWORD, 'new_password': NEW_PASSWORD},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.access_token}',
            **headers,
        )

    def test_gives_new_app_tokens(self):
        response = self.change()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)
        self.assertEqual(self.app_refresh(response.data['refresh_token']).status_code, status.HTTP_200_OK)

    def test_old_token_stops_working(self):
        self.change()

        self.assertEqual(self.app_refresh(self.refresh_token).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refuses_browser_request(self):
        response = self.change(HTTP_ORIGIN='https://example.com')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_wrong_current_password_is_refused(self):
        response = APIClient().post(
            APP_PASSWORD_CHANGE_URL,
            {'current_password': 'wrong-password-here', 'new_password': NEW_PASSWORD},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.access_token}',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('current_password', response.data['errors'])
