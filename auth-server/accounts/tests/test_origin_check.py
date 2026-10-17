# auth-server/accounts/tests/test_origin_check.py

"""
refresh 쿠키를 쓰는 주소(refresh, logout)가 허용한 출처의 요청만 받는지 확인한다.

거부할 때는 쿠키를 건드리지 않아야 한다. 토큰을 돌리거나 지우면 다른 곳의 페이지가
사용자의 세션을 바꿀 수 있다. 그것이 이 검사로 막으려는 일이다.
"""

from django.test import override_settings
from rest_framework import status
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.tests.test_refresh import LOGOUT_ALL_URL, LOGOUT_URL, REFRESH_URL, RefreshTestCase

# 화면을 여는 주소와, 같은 사이트의 다른 하위 도메인
PLAY_ORIGIN = 'https://play.example.com'
CHAT_ORIGIN = 'https://chat.example.com'


@override_settings(REFRESH_COOKIE_ALLOWED_ORIGINS=[PLAY_ORIGIN])
class OriginCheckTestCase(RefreshTestCase):
    """허용 목록이 PLAY_ORIGIN 하나인 상태에서 로그인해 둔다."""

    def post_from(self, url: str, origin: str | None):
        """주어진 Origin 으로 보낸다. None 이면 Origin 을 싣지 않는다."""
        if origin is None:
            del self.client.defaults['HTTP_ORIGIN']
            return self.client.post(url)
        return self.client.post(url, HTTP_ORIGIN=origin)

    def assert_refused(self, response) -> None:
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'origin_not_allowed')
        # 쿠키를 지우지도, 새로 심지도 않는다
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)

    def assert_session_untouched(self) -> None:
        """거부된 요청 뒤에도 처음의 refresh 토큰을 그대로 쓸 수 있다."""
        self.assertFalse(BlacklistedToken.objects.exists())
        self.assertEqual(self.post_from(REFRESH_URL, PLAY_ORIGIN).status_code, status.HTTP_200_OK)


class RefreshOriginTests(OriginCheckTestCase):
    def test_allowed_origin_refreshes(self):
        response = self.post_from(REFRESH_URL, PLAY_ORIGIN)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_origin_is_compared_without_case(self):
        response = self.post_from(REFRESH_URL, 'HTTPS://Play.Example.com')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_missing_origin_is_refused(self):
        self.assert_refused(self.post_from(REFRESH_URL, None))
        self.client.defaults['HTTP_ORIGIN'] = PLAY_ORIGIN
        self.assert_session_untouched()

    def test_null_origin_is_refused(self):
        self.assert_refused(self.post_from(REFRESH_URL, 'null'))
        self.assert_session_untouched()

    def test_other_subdomain_of_the_same_site_is_refused(self):
        self.assert_refused(self.post_from(REFRESH_URL, CHAT_ORIGIN))
        self.assert_session_untouched()

    def test_only_the_whole_origin_matches(self):
        for origin in (
            'https://play.example.com.evil.test',
            'http://play.example.com',
            'https://play.example.com:8443',
        ):
            with self.subTest(origin=origin):
                self.assert_refused(self.post_from(REFRESH_URL, origin))
        self.assert_session_untouched()

    def test_refusal_is_checked_before_the_cookie(self):
        # 쿠키가 없어도 출처부터 본다. 다른 곳의 페이지는 세션이 있는지조차 알 수 없다
        del self.client.cookies[REFRESH_COOKIE_NAME]

        self.assert_refused(self.post_from(REFRESH_URL, CHAT_ORIGIN))


class LogoutOriginTests(OriginCheckTestCase):
    def test_allowed_origin_logs_out(self):
        response = self.post_from(LOGOUT_URL, PLAY_ORIGIN)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_other_origin_cannot_log_the_user_out(self):
        self.assert_refused(self.post_from(LOGOUT_URL, CHAT_ORIGIN))
        self.assert_session_untouched()

    def test_missing_origin_is_refused(self):
        self.assert_refused(self.post_from(LOGOUT_URL, None))
        self.client.defaults['HTTP_ORIGIN'] = PLAY_ORIGIN
        self.assert_session_untouched()

    def test_logout_all_does_not_look_at_the_origin(self):
        # access 토큰(Authorization)으로 본인을 확인하는 주소다. 다른 곳의 페이지는 그 토큰을 실을 수 없다
        access_token = self.login_response.data['access_token']
        del self.client.defaults['HTTP_ORIGIN']

        response = self.client.post(LOGOUT_ALL_URL, HTTP_AUTHORIZATION=f'Bearer {access_token}')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class RefusalLogTests(OriginCheckTestCase):
    def test_refusal_is_logged_with_a_shortened_origin(self):
        long_origin = 'https://' + 'a' * 300 + '.example.com'

        with self.assertLogs('accounts.origin_check', level='WARNING') as logs:
            self.post_from(REFRESH_URL, long_origin)

        line = logs.output[0]
        self.assertIn(f'path={REFRESH_URL}', line)
        self.assertIn('a' * 92, line)
        self.assertNotIn('a' * 93, line)

    def test_cookie_is_not_logged(self):
        refresh_token = self.refresh_cookie_value()

        with self.assertLogs('accounts.origin_check', level='WARNING') as logs:
            self.post_from(REFRESH_URL, CHAT_ORIGIN)

        self.assertNotIn(refresh_token, '\n'.join(logs.output))
