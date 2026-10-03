# auth-server/accounts/tests/test_login_ip_block.py

"""
예약어 아이디(admin, root 등)로 로그인을 시도한 IP 를 막는 것을 검증한다. 실제 Redis 에서 돈다.

막힌 IP 는 막혔다는 것을 알 수 없어야 한다. 평소의 거절과 같은 응답을 받는다.
"""

from unittest.mock import patch

import redis
from django.core import mail
from rest_framework import status

from accounts.attempt_policies import LOGIN_FAILURES_PER_ACCOUNT_AND_IP, LOGIN_IP_BLOCK
from accounts.models import SecurityEvent, SecurityEventKind
from accounts.tests.test_attempt_policies import (
    IP,
    OTHER_IP,
    RESET_URL,
    WRONG_PASSWORD,
    AttemptPolicyTestCase,
    create_user,
)
from config.redis_client import get_redis


class LoginIpBlockTests(AttemptPolicyTestCase):
    def setUp(self):
        super().setUp()
        create_user()

    def try_reserved_username(self, username: str = 'admin', ip: str = IP):
        return self.login(username=username, password=WRONG_PASSWORD, ip=ip)

    def assert_rejected_like_a_wrong_password(self, response) -> None:
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {'detail': '아이디 또는 비밀번호가 올바르지 않습니다.'})
        self.assertNotIn('Retry-After', response)

    def test_the_reserved_attempt_itself_looks_like_a_wrong_password(self):
        self.assert_rejected_like_a_wrong_password(self.try_reserved_username())

    def test_blocks_the_right_password_from_that_ip(self):
        self.try_reserved_username()

        response = self.login()

        # 429 가 아니다. 막혔다는 것을 알려 주면 IP 를 바꿔 다시 시도한다
        self.assert_rejected_like_a_wrong_password(response)
        self.assertEqual(len(mail.outbox), 0)

    def test_does_not_block_other_ips(self):
        self.try_reserved_username()

        response = self.login(ip=OTHER_IP)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_ignores_case_and_spaces(self):
        self.try_reserved_username(username='  Admin ')

        self.assert_rejected_like_a_wrong_password(self.login())

    def test_a_name_that_only_contains_a_reserved_word_is_not_blocked(self):
        self.try_reserved_username(username='admin_fan')

        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)

    def test_only_login_is_blocked(self):
        self.try_reserved_username()

        # 같은 IP 를 쓰는 다른 사람(공유기 뒤)의 피해를 줄인다. 로그인만 막는다
        response = self.client.post(RESET_URL, {'email': 'someone@example.com'}, format='json', REMOTE_ADDR=IP)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_block_ends_after_the_window(self):
        self.try_reserved_username()
        key = next(get_redis().scan_iter(match=f'*:{LOGIN_IP_BLOCK.name}:*'))

        seconds_left = get_redis().ttl(key)
        # 시간이 지난 것처럼 키를 없앤다
        get_redis().delete(key)

        self.assertGreater(seconds_left, 0)
        self.assertLessEqual(seconds_left, LOGIN_IP_BLOCK.window.total_seconds())
        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)

    def test_spends_the_time_of_a_password_check_while_blocked(self):
        self.try_reserved_username()

        with patch('accounts.views.spend_password_check_time') as spend:
            self.login()

        # 바로 응답하면 평소의 거절보다 빨라서, 응답 시간으로 막혔다는 것이 드러난다
        spend.assert_called_once()

    def test_attempts_while_blocked_do_not_count_as_password_failures(self):
        self.try_reserved_username()
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts)
        # 차단이 풀린 것처럼 키를 없앤다
        get_redis().delete(next(get_redis().scan_iter(match=f'*:{LOGIN_IP_BLOCK.name}:*')))

        # 막힌 동안에는 비밀번호를 확인하지 않았다. 틀린 횟수로 세지도 않는다
        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)

    def test_redis_down_does_not_block(self):
        with patch('accounts.attempt_limits.get_redis', side_effect=redis.ConnectionError('down')):
            with self.assertLogs('accounts.attempt_limits', level='WARNING'):
                self.try_reserved_username()
                response = self.login()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)


class LoginIpBlockEventTests(AttemptPolicyTestCase):
    def test_records_the_block_once(self):
        for username in ['admin', 'root', 'administrator']:
            self.login(username=username, password=WRONG_PASSWORD)

        # 둘째부터는 이미 막힌 IP 다
        event = SecurityEvent.objects.get()
        self.assertEqual(event.kind, SecurityEventKind.RESERVED_USERNAME_LOGIN)
        self.assertEqual(event.ip, IP)
        self.assertIsNone(event.user)

    def test_each_ip_is_recorded(self):
        self.login(username='admin', password=WRONG_PASSWORD)
        self.login(username='admin', password=WRONG_PASSWORD, ip=OTHER_IP)

        self.assertEqual(SecurityEvent.objects.count(), 2)

    def test_ordinary_wrong_usernames_are_not_recorded(self):
        self.login(username='nobody_here', password=WRONG_PASSWORD)

        self.assertEqual(SecurityEvent.objects.count(), 0)
