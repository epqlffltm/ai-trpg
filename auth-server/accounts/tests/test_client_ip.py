# auth-server/accounts/tests/test_client_ip.py

"""
요청을 보낸 쪽의 IP 주소를 알아내는 규칙을 검증한다.
"""

from django.test import RequestFactory, SimpleTestCase, override_settings

from accounts.client_ip import get_attempt_subject, get_client_ip

CLIENT = '203.0.113.7'
PROXY = '10.0.0.5'
OUTER_PROXY = '198.51.100.9'
FAKE = '1.2.3.4'


def make_request(remote_addr: str, forwarded_for: str | None = None):
    headers = {'REMOTE_ADDR': remote_addr}
    if forwarded_for is not None:
        headers['HTTP_X_FORWARDED_FOR'] = forwarded_for
    return RequestFactory().get('/', **headers)


@override_settings(TRUSTED_PROXY_COUNT=0)
class NoProxyTests(SimpleTestCase):
    """프록시가 없는 구성. 서버에 직접 연결한 상대의 주소만 믿는다."""

    def test_uses_the_connecting_address(self):
        self.assertEqual(get_client_ip(make_request(CLIENT)), CLIENT)

    def test_ignores_the_forwarded_header(self):
        request = make_request(CLIENT, forwarded_for=FAKE)

        # 헤더는 요청을 보내는 쪽이 마음대로 적을 수 있다
        self.assertEqual(get_client_ip(request), CLIENT)


@override_settings(TRUSTED_PROXY_COUNT=1)
class OneProxyTests(SimpleTestCase):
    """프록시가 하나인 구성. 프록시가 적은 마지막 주소를 믿는다."""

    def test_uses_the_address_the_proxy_added(self):
        request = make_request(PROXY, forwarded_for=CLIENT)

        self.assertEqual(get_client_ip(request), CLIENT)

    def test_ignores_addresses_the_client_made_up(self):
        # 요청을 보낸 쪽이 헤더에 가짜 주소를 미리 적어 보냈다.
        # 프록시는 그 뒤에 진짜 주소를 붙인다
        request = make_request(PROXY, forwarded_for=f'{FAKE}, 5.6.7.8, {CLIENT}')

        self.assertEqual(get_client_ip(request), CLIENT)

    def test_falls_back_when_the_header_is_missing(self):
        # 프록시를 건너뛰고 서버에 직접 온 요청
        self.assertEqual(get_client_ip(make_request(CLIENT)), CLIENT)

    def test_falls_back_when_the_header_is_not_an_address(self):
        request = make_request(PROXY, forwarded_for='not-an-address')

        self.assertEqual(get_client_ip(request), PROXY)

    def test_tolerates_spaces(self):
        request = make_request(PROXY, forwarded_for=f'  {FAKE} ,   {CLIENT}  ')

        self.assertEqual(get_client_ip(request), CLIENT)


@override_settings(TRUSTED_PROXY_COUNT=2)
class TwoProxyTests(SimpleTestCase):
    """프록시가 둘인 구성(예: CDN 뒤에 로드밸런서). 뒤에서 두 번째 주소를 믿는다."""

    def test_uses_the_address_the_outer_proxy_added(self):
        # 바깥 프록시가 요청자의 주소를, 안쪽 프록시가 바깥 프록시의 주소를 붙였다
        request = make_request(PROXY, forwarded_for=f'{CLIENT}, {OUTER_PROXY}')

        self.assertEqual(get_client_ip(request), CLIENT)

    def test_ignores_addresses_the_client_made_up(self):
        request = make_request(PROXY, forwarded_for=f'{FAKE}, {CLIENT}, {OUTER_PROXY}')

        self.assertEqual(get_client_ip(request), CLIENT)

    def test_falls_back_when_the_header_is_shorter_than_expected(self):
        request = make_request(CLIENT, forwarded_for=FAKE)

        # 있어야 할 만큼의 주소가 없으면 헤더를 믿지 않는다
        self.assertEqual(get_client_ip(request), CLIENT)


@override_settings(TRUSTED_PROXY_COUNT=0)
class NormalizationTests(SimpleTestCase):
    def test_ipv4_written_as_ipv6_becomes_ipv4(self):
        request = make_request(f'::ffff:{CLIENT}')

        # 같은 주소가 표기만 달라 따로 세어지면 안 된다
        self.assertEqual(get_client_ip(request), CLIENT)

    def test_ipv6_is_written_one_way(self):
        request = make_request('2001:0DB8:0000:0000:0000:0000:0000:0001')

        self.assertEqual(get_client_ip(request), '2001:db8::1')


@override_settings(TRUSTED_PROXY_COUNT=0)
class AttemptSubjectTests(SimpleTestCase):
    """시도 횟수를 셀 때 "같은 곳" 으로 보는 단위."""

    def test_ipv4_is_counted_per_address(self):
        self.assertEqual(get_attempt_subject(make_request(CLIENT)), CLIENT)
        self.assertNotEqual(
            get_attempt_subject(make_request('203.0.113.7')),
            get_attempt_subject(make_request('203.0.113.8')),
        )

    def test_ipv6_addresses_in_the_same_block_are_counted_together(self):
        first = get_attempt_subject(make_request('2001:db8:1:2::1'))
        second = get_attempt_subject(make_request('2001:db8:1:2:ffff:ffff:ffff:ffff'))

        # 한 가입자가 가진 주소 묶음 안에서 주소를 바꿔도 같은 곳으로 센다
        self.assertEqual(first, second)
        self.assertEqual(first, '2001:db8:1:2::/64')

    def test_ipv6_addresses_in_different_blocks_are_counted_apart(self):
        first = get_attempt_subject(make_request('2001:db8:1:2::1'))
        second = get_attempt_subject(make_request('2001:db8:1:3::1'))

        self.assertNotEqual(first, second)
