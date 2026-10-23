# auth-server/accounts/tests/test_network_blocks.py

"""
IP 주소나 대역으로 가입, 로그인, 토큰 갱신을 막는 것(#638, accounts/network_blocks.py)을 검증한다.

  - 적는 규칙: 주소 하나는 IPv4 /32, IPv6 /64. 대역의 뒤쪽 비트는 0 으로 맞춘다. IPv4 /16, IPv6 /32 보다 넓으면 거절.
    기간은 1~365일
  - 찾기: 대역 안의 주소만, 기간이 지나지 않은 것만. 주소가 아닌 글이면 막지 않는다
  - 거절: 가입의 세 단계, 로그인의 세 주소, 토큰 갱신이 403 network_blocked 다. 막혔다고 알린다.
    로그인은 비밀번호를 확인하지 않고 메일도 보내지 않는다. 갱신은 쿠키를 지우지 않는다. 메트릭에 센다
  - 관리 명령(block_network, unblock_network), 관리 화면(조회와 지우기만), 정리(send_security_digest)
"""

import ipaddress
from datetime import timedelta
from io import StringIO

from django.contrib import admin
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.models import NetworkBlock, User
from accounts.network_blocks import (
    MAX_DAYS,
    InvalidDaysError,
    InvalidNetworkError,
    block_network,
    clean_days,
    delete_expired_network_blocks,
    find_block,
    parse_network,
    unblock_network,
)
from accounts.tests.helpers import (
    LOGIN_URL,
    LOGIN_VERIFY_URL,
    SIGNUP_COMPLETE_URL,
    SIGNUP_URL,
    SIGNUP_VERIFY_URL,
    BrowserClient,
    log_in,
)
from accounts.tests.test_attempt_policies import PASSWORD, USERNAME, create_user
from observability.tests.metrics import record_metrics

BLOCKED_IP = '198.51.100.23'
FREE_IP = '198.51.100.99'
REFRESH_URL = '/api/v1/auth/refresh'
RESEND_URL = '/api/v1/auth/login/resend'


def net(text: str):
    return ipaddress.ip_network(text)


class ParseTests(TestCase):
    def test_one_address_is_one_household(self):
        self.assertEqual(parse_network(' 198.51.100.23 '), net('198.51.100.23/32'))
        self.assertEqual(parse_network('2001:db8:1:2::7'), net('2001:db8:1:2::/64'))
        self.assertEqual(parse_network('::ffff:198.51.100.23'), net('198.51.100.23/32'))

    def test_a_range_keeps_its_size_and_clears_the_host_bits(self):
        self.assertEqual(parse_network('198.51.100.23/24'), net('198.51.100.0/24'))
        self.assertEqual(parse_network('2001:db8::/48'), net('2001:db8::/48'))
        self.assertEqual(parse_network('::ffff:198.51.100.0/120'), net('198.51.100.0/24'))

    def test_too_wide_or_not_an_address_is_refused(self):
        for text in ('10.0.0.0/8', '0.0.0.0/0', '2001:db8::/16', '', 'example.com', '198.51.100.300'):
            with self.subTest(text=text), self.assertRaises(InvalidNetworkError):
                parse_network(text)
        self.assertEqual(parse_network('10.1.0.0/16'), net('10.1.0.0/16'))

    def test_days_are_one_to_a_year(self):
        self.assertEqual(clean_days(1), 1)
        self.assertEqual(clean_days(MAX_DAYS), MAX_DAYS)
        for days in (0, -1, MAX_DAYS + 1):
            with self.subTest(days=days), self.assertRaises(InvalidDaysError):
                clean_days(days)


class StoreTests(TestCase):
    def test_find_matches_addresses_inside_the_range_until_it_expires(self):
        now = timezone.now()
        block, created = block_network(net('198.51.100.0/24'), 30, '불법 행위', now)

        self.assertTrue(created)
        self.assertEqual(find_block(BLOCKED_IP, now), block)
        self.assertIsNone(find_block('198.51.101.1', now))
        self.assertIsNone(find_block(BLOCKED_IP, now + timedelta(days=30)))
        # 프록시 설정이 어긋나 주소가 아닌 글이 와도 막지 않고 멈추지 않는다
        self.assertIsNone(find_block('', now))

    def test_an_ipv6_household_is_matched_by_any_address_in_it(self):
        now = timezone.now()
        block_network(parse_network('2001:db8:1:2::7'), 30, '불법 행위', now)

        self.assertIsNotNone(find_block('2001:db8:1:2:ffff::1', now))
        self.assertIsNone(find_block('2001:db8:1:3::1', now))

    def test_blocking_again_replaces_the_period_and_reason(self):
        now = timezone.now()
        block_network(net(f'{BLOCKED_IP}/32'), 30, '처음', now)

        block, created = block_network(net(f'{BLOCKED_IP}/32'), 7, '다시', now)

        self.assertFalse(created)
        self.assertEqual((block.note, block.expires_at), ('다시', now + timedelta(days=7)))
        self.assertEqual(NetworkBlock.objects.count(), 1)
        self.assertEqual(NetworkBlock.objects.get().network, net(f'{BLOCKED_IP}/32'))

    def test_unblock_and_cleanup(self):
        now = timezone.now()
        block_network(net(f'{BLOCKED_IP}/32'), 1, '짧게', now)
        block_network(net(f'{FREE_IP}/32'), 30, '길게', now)

        self.assertEqual(delete_expired_network_blocks(now + timedelta(days=2)), 1)
        self.assertTrue(unblock_network(net(f'{FREE_IP}/32')))
        self.assertFalse(unblock_network(net(f'{FREE_IP}/32')))
        self.assertFalse(NetworkBlock.objects.exists())


@override_settings(ATTEMPT_LIMITS_ENABLED=False, TRUSTED_PROXY_COUNT=0)
class RefusalTests(APITestCase):
    client_class = BrowserClient

    def setUp(self):
        self.metrics = record_metrics(self)
        block_network(net(f'{BLOCKED_IP}/32'), 30, '불법 행위', timezone.now())

    def assert_blocked(self, response) -> None:
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'network_blocked')
        self.assertIn('제한되었습니다', response.data['detail'])

    def test_every_signup_step_is_refused_without_mail(self):
        bodies = {SIGNUP_URL: {'email': 'new@example.com'}, SIGNUP_VERIFY_URL: {}, SIGNUP_COMPLETE_URL: {}}
        for url, body in bodies.items():
            with self.subTest(url=url):
                self.assert_blocked(self.client.post(url, body, format='json', REMOTE_ADDR=BLOCKED_IP))

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.metrics.value('auth_network_blocked', endpoint='signup'), 3)

    def test_login_is_refused_even_with_the_right_password(self):
        create_user()

        response = self.client.post(
            LOGIN_URL, {'username': USERNAME, 'password': PASSWORD}, format='json', REMOTE_ADDR=BLOCKED_IP
        )

        self.assert_blocked(response)
        self.assertEqual(len(mail.outbox), 0)
        for url in (LOGIN_VERIFY_URL, RESEND_URL):
            with self.subTest(url=url):
                self.assert_blocked(self.client.post(url, {}, format='json', REMOTE_ADDR=BLOCKED_IP))
        self.assertEqual(self.metrics.value('auth_network_blocked', endpoint='login'), 3)

    def test_refresh_is_refused_and_the_cookie_is_kept(self):
        create_user()
        log_in(self.client, USERNAME, PASSWORD)

        response = self.client.post(REFRESH_URL, REMOTE_ADDR=BLOCKED_IP)

        self.assert_blocked(response)
        # 쿠키를 지우지 않는다. 다른 네트워크로 옮기면 로그인한 채로 이어 간다
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)
        self.assertEqual(self.client.post(REFRESH_URL, REMOTE_ADDR=FREE_IP).status_code, status.HTTP_200_OK)
        self.assertEqual(self.metrics.value('auth_network_blocked', endpoint='refresh'), 1)

    def test_other_addresses_and_expired_blocks_pass(self):
        self.assertEqual(
            self.client.post(SIGNUP_URL, {'email': 'a@example.com'}, format='json', REMOTE_ADDR=FREE_IP).status_code,
            status.HTTP_202_ACCEPTED,
        )
        NetworkBlock.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(
            self.client.post(SIGNUP_URL, {'email': 'b@example.com'}, format='json', REMOTE_ADDR=BLOCKED_IP).status_code,
            status.HTTP_202_ACCEPTED,
        )


class CommandTests(TestCase):
    def run_command(self, *args) -> str:
        output = StringIO()
        call_command(*args, stdout=output)
        return output.getvalue()

    def test_block_and_unblock(self):
        output = self.run_command('block_network', '2001:db8:1:2::7', '--reason', ' 불법 행위 ', '--days', '7')

        block = NetworkBlock.objects.get()
        self.assertEqual((block.network, block.note), (net('2001:db8:1:2::/64'), '불법 행위'))
        self.assertIn('2001:db8:1:2::/64 를', output)
        self.assertIn('이미 막혀', self.run_command('block_network', '2001:db8:1:2::8', '--reason', '다시'))
        self.assertIn('풀었습니다', self.run_command('unblock_network', '2001:db8:1:2::1'))
        self.assertIn('없습니다', self.run_command('unblock_network', '2001:db8:1:2::1'))

    def test_the_default_period_is_thirty_days(self):
        before = timezone.now()
        self.run_command('block_network', BLOCKED_IP, '--reason', '불법 행위')

        expires_at = NetworkBlock.objects.get().expires_at
        self.assertGreaterEqual(expires_at, before + timedelta(days=30))
        self.assertLess(expires_at, before + timedelta(days=30, minutes=1))

    def test_bad_input_is_refused(self):
        cases = [
            ('block_network', '10.0.0.0/8', '--reason', '넓다'),
            ('block_network', BLOCKED_IP, '--reason', '길다', '--days', str(MAX_DAYS + 1)),
            ('block_network', BLOCKED_IP, '--reason', '  '),
            ('unblock_network', 'nope'),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(CommandError):
                self.run_command(*args)
        self.assertFalse(NetworkBlock.objects.exists())

    def test_the_digest_deletes_expired_blocks(self):
        block_network(net(f'{BLOCKED_IP}/32'), 1, '짧게', timezone.now() - timedelta(days=2))

        output = self.run_command('send_security_digest')

        self.assertIn('지운 IP 막기 1건', output)
        self.assertFalse(NetworkBlock.objects.exists())


class AdminTests(TestCase):
    def test_the_screen_reads_and_deletes_only(self):
        model_admin = admin.site._registry[NetworkBlock]
        request = type('Request', (), {'user': User(is_superuser=True, is_staff=True)})()

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertTrue(model_admin.has_delete_permission(request))
