# auth-server/accounts/tests/test_login_ip_block.py

"""
예약어 아이디(admin, root 등)로 로그인을 반복해 시도한 IP 를 막는 것을 검증한다. 실제 Redis 에서 돈다.

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

    def get_blocked(self, username: str = 'admin', ip: str = IP) -> None:
        """예약어 아이디로 한도만큼 시도해서 그 IP 가 막히게 한다."""
        for _ in range(LOGIN_IP_BLOCK.max_attempts):
            self.try_reserved_username(username=username, ip=ip)

    def assert_rejected_like_a_wrong_password(self, response) -> None:
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {'detail': '아이디 또는 비밀번호가 올바르지 않습니다.'})
        self.assertNotIn('Retry-After', response)

    def test_the_reserved_attempt_itself_looks_like_a_wrong_password(self):
        self.assert_rejected_like_a_wrong_password(self.try_reserved_username())

    def test_does_not_block_below_the_limit(self):
        for _ in range(LOGIN_IP_BLOCK.max_attempts - 1):
            self.try_reserved_username()

        # 한 번의 호기심으로 같은 IP 의 모두가 막히지는 않는다
        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)

    def test_different_reserved_names_are_counted_together(self):
        for username in ['admin', 'root', 'administrator'][:LOGIN_IP_BLOCK.max_attempts]:
            self.try_reserved_username(username=username)

        # 이름을 바꿔 가며 찔러 보는 것이 탐색의 전형이다
        self.assert_rejected_like_a_wrong_password(self.login())

    def test_blocks_the_right_password_from_that_ip(self):
        self.get_blocked()

        response = self.login()

        # 429 가 아니다. 막혔다는 것을 알려 주면 IP 를 바꿔 다시 시도한다
        self.assert_rejected_like_a_wrong_password(response)
        self.assertEqual(len(mail.outbox), 0)

    def test_does_not_block_other_ips(self):
        self.get_blocked()

        response = self.login(ip=OTHER_IP)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_ignores_case_and_spaces(self):
        self.get_blocked(username='  Admin ')

        self.assert_rejected_like_a_wrong_password(self.login())

    def test_a_name_that_only_contains_a_reserved_word_is_not_blocked(self):
        self.get_blocked(username='admin_fan')

        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)

    def test_only_login_is_blocked(self):
        self.get_blocked()

        # 같은 IP 를 쓰는 다른 사람(공유기 뒤)의 피해를 줄인다. 로그인만 막는다
        response = self.client.post(RESET_URL, {'email': 'someone@example.com'}, format='json', REMOTE_ADDR=IP)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_block_ends_after_the_window(self):
        self.get_blocked()
        key = next(get_redis().scan_iter(match=f'*:{LOGIN_IP_BLOCK.name}:*'))

        seconds_left = get_redis().ttl(key)
        # 시간이 지난 것처럼 키를 없앤다
        get_redis().delete(key)

        self.assertGreater(seconds_left, 0)
        self.assertLessEqual(seconds_left, LOGIN_IP_BLOCK.window.total_seconds())
        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)

    def test_spends_the_time_of_a_password_check_while_blocked(self):
        self.get_blocked()

        with patch('accounts.views.spend_password_check_time') as spend:
            self.login()

        # 바로 응답하면 평소의 거절보다 빨라서, 응답 시간으로 막혔다는 것이 드러난다
        spend.assert_called_once()

    def test_attempts_while_blocked_do_not_count_as_password_failures(self):
        self.get_blocked()
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts)
        # 차단이 풀린 것처럼 키를 없앤다
        get_redis().delete(next(get_redis().scan_iter(match=f'*:{LOGIN_IP_BLOCK.name}:*')))

        # 막힌 동안에는 비밀번호를 확인하지 않았다. 틀린 횟수로 세지도 않는다
        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)

    def test_redis_down_does_not_block(self):
        with patch('accounts.attempt_limits.get_redis', side_effect=redis.ConnectionError('down')):
            with self.assertLogs('accounts.attempt_limits', level='WARNING'):
                self.get_blocked()
                response = self.login()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)


class LoginIpBlockEventTests(AttemptPolicyTestCase):
    def try_reserved(self, times: int, ip: str = IP) -> None:
        for _ in range(times):
            self.login(username='admin', password=WRONG_PASSWORD, ip=ip)

    def test_nothing_is_recorded_below_the_limit(self):
        self.try_reserved(LOGIN_IP_BLOCK.max_attempts - 1)

        self.assertEqual(SecurityEvent.objects.count(), 0)

    def test_records_the_block_once(self):
        # 한도를 채운 뒤에도 계속 시도한다. 그때는 이미 막힌 IP 다
        self.try_reserved(LOGIN_IP_BLOCK.max_attempts + 5)

        event = SecurityEvent.objects.get()
        self.assertEqual(event.kind, SecurityEventKind.RESERVED_USERNAME_LOGIN)
        self.assertEqual(event.ip, IP)
        self.assertIsNone(event.user)

    def test_each_ip_is_recorded(self):
        self.try_reserved(LOGIN_IP_BLOCK.max_attempts)
        self.try_reserved(LOGIN_IP_BLOCK.max_attempts, ip=OTHER_IP)

        self.assertEqual(SecurityEvent.objects.count(), 2)

    def test_ordinary_wrong_usernames_are_not_recorded(self):
        for _ in range(LOGIN_IP_BLOCK.max_attempts):
            self.login(username='nobody_here', password=WRONG_PASSWORD)

        self.assertEqual(SecurityEvent.objects.count(), 0)
