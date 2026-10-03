# auth-server/accounts/tests/test_security_events.py

"""
보안 이벤트가 남는 순간을 검증한다. 실제 Redis 에서 돈다.

이벤트는 "막히기 시작한 순간" 에 한 번만 남아야 한다.
막힌 뒤에도 계속 들어오는 요청마다 남으면, 공격자가 요청 수만큼 DB 에 행을 쌓을 수 있다.
"""

from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase
from rest_framework import status

from accounts.attempt_policies import (
    LOGIN_FAILURES_PER_ACCOUNT_AND_IP,
    LOGIN_PER_IP,
    PASSWORD_CHANGE_FAILURES_PER_USER,
    PASSWORD_RESET_PER_IP,
    SIGNUP_PER_IP,
    SIGNUP_RESEND_PER_IP,
)
from accounts.models import SecurityEvent, SecurityEventKind
from accounts.tests.helpers import LOGIN_URL, log_in
from accounts.tests.test_attempt_policies import (
    CHANGE_URL,
    IP,
    NEW_PASSWORD,
    OTHER_IP,
    PASSWORD,
    RESET_URL,
    SIGNUP_RESEND_URL,
    SIGNUP_URL,
    USERNAME,
    WRONG_PASSWORD,
    AttemptPolicyTestCase,
    create_user,
)


class LoginFailureEventTests(AttemptPolicyTestCase):
    def setUp(self):
        super().setUp()
        self.user = create_user()

    def get_blocked(self, **kwargs) -> None:
        """한도까지 틀린 뒤 한 번 더 시도해서 막힌다."""
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts, **kwargs)
        self.assert_too_many_attempts(self.login(password=WRONG_PASSWORD, **kwargs))

    def test_nothing_is_recorded_up_to_the_limit(self):
        # 한도까지는 허용된 시도다. 아직 막힌 것이 아니다
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts)

        self.assertEqual(SecurityEvent.objects.count(), 0)

    def test_records_the_moment_the_block_starts(self):
        self.get_blocked()

        event = SecurityEvent.objects.get()
        self.assertEqual(event.kind, SecurityEventKind.LOGIN_FAILURES_LIMITED)
        self.assertEqual(event.ip, IP)
        self.assertEqual(event.user, self.user)

    def test_requests_after_the_block_do_not_add_events(self):
        self.get_blocked()

        for _ in range(5):
            self.assert_too_many_attempts(self.login(password=WRONG_PASSWORD))

        self.assertEqual(SecurityEvent.objects.count(), 1)

    def test_unknown_username_is_recorded_without_an_account(self):
        self.get_blocked(username='nobody_here')

        event = SecurityEvent.objects.get()
        self.assertIsNone(event.user)
        self.assertEqual(event.ip, IP)

    def test_each_ip_gets_its_own_event(self):
        self.get_blocked()
        self.get_blocked(ip=OTHER_IP)

        self.assertEqual(
            sorted(SecurityEvent.objects.values_list('ip', flat=True)),
            sorted([IP, OTHER_IP]),
        )

    def test_event_survives_when_the_account_is_deleted(self):
        self.get_blocked()

        self.user.delete()

        self.assertIsNone(SecurityEvent.objects.get().user)


class IpLimitEventTests(AttemptPolicyTestCase):
    """IP 별 제한(throttle)에 걸렸을 때."""

    def post_many(self, url: str, body: dict, times: int):
        for _ in range(times):
            response = self.client.post(url, body, format='json', REMOTE_ADDR=IP)
        return response

    def assert_one_event(self, kind: str) -> None:
        event = SecurityEvent.objects.get()
        self.assertEqual(event.kind, kind)
        self.assertEqual(event.ip, IP)
        self.assertIsNone(event.user)

    def test_login(self):
        # 제한을 넘긴 뒤에도 다섯 번 더 보낸다. 이벤트는 하나여야 한다
        response = self.post_many(LOGIN_URL, {}, LOGIN_PER_IP.max_attempts + 5)

        self.assert_too_many_attempts(response)
        self.assert_one_event(SecurityEventKind.LOGIN_IP_LIMITED)

    def test_signup(self):
        response = self.post_many(SIGNUP_URL, {}, SIGNUP_PER_IP.max_attempts + 5)

        self.assert_too_many_attempts(response)
        self.assert_one_event(SecurityEventKind.SIGNUP_IP_LIMITED)

    def test_signup_resend(self):
        response = self.post_many(SIGNUP_RESEND_URL, {}, SIGNUP_RESEND_PER_IP.max_attempts + 5)

        self.assert_too_many_attempts(response)
        self.assert_one_event(SecurityEventKind.SIGNUP_RESEND_IP_LIMITED)

    def test_password_reset(self):
        response = self.post_many(RESET_URL, {}, PASSWORD_RESET_PER_IP.max_attempts + 5)

        self.assert_too_many_attempts(response)
        self.assert_one_event(SecurityEventKind.PASSWORD_RESET_IP_LIMITED)

    def test_nothing_is_recorded_at_the_limit(self):
        # 허용된 마지막 요청까지는 막힌 것이 아니다
        self.post_many(RESET_URL, {}, PASSWORD_RESET_PER_IP.max_attempts)

        self.assertEqual(SecurityEvent.objects.count(), 0)


class PasswordChangeEventTests(AttemptPolicyTestCase):
    def setUp(self):
        super().setUp()
        self.user = create_user()
        access_token = log_in(self.client, USERNAME, PASSWORD).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

    def change(self, current_password: str):
        body = {'current_password': current_password, 'new_password': NEW_PASSWORD}
        return self.client.post(CHANGE_URL, body, format='json', REMOTE_ADDR=IP)

    def test_records_the_moment_the_block_starts(self):
        for _ in range(PASSWORD_CHANGE_FAILURES_PER_USER.max_attempts):
            self.assertEqual(self.change(WRONG_PASSWORD).status_code, status.HTTP_400_BAD_REQUEST)
        # 막힌 뒤의 요청
        self.assert_too_many_attempts(self.change(WRONG_PASSWORD))

        event = SecurityEvent.objects.get()
        self.assertEqual(event.kind, SecurityEventKind.PASSWORD_CHANGE_FAILURES_LIMITED)
        self.assertEqual(event.user, self.user)
        # 횟수는 사용자로 세지만, 어디서 시도했는지는 남긴다
        self.assertEqual(event.ip, IP)


class SecurityEventAdminTests(SimpleTestCase):
    """관리자 화면에서는 조회만 된다. 만들거나 고치거나 지울 수 있으면 기록으로서 믿을 수 없다."""

    def setUp(self):
        self.model_admin = admin.site.get_model_admin(SecurityEvent)
        self.request = RequestFactory().get('/admin/')

    def test_cannot_add(self):
        self.assertFalse(self.model_admin.has_add_permission(self.request))

    def test_cannot_change(self):
        self.assertFalse(self.model_admin.has_change_permission(self.request))

    def test_cannot_delete(self):
        self.assertFalse(self.model_admin.has_delete_permission(self.request))
