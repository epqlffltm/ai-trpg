# .github/scripts/test_port_scope.py

"""
열린 포트의 검사(port_scope.py)의 규칙을 본다. compose 없이, 작은 설정을 만들어 넣는다.

    사용: python3 -m unittest discover -s .github/scripts -p 'test_*_scope.py'

stack-smoke.sh 의 check 가 실제 설정을 검사하기 전에 부른다. 규칙이 틀리면 열린 포트를 놓치고 초록이 된다.
"""

import unittest

from port_scope import PUBLIC_PORTS, Binding, allowed_public_ports, check, parse_short


def config(**services: dict) -> dict:
    return {'services': services}


class ParseShortTests(unittest.TestCase):
    def test_reads_the_address_only_when_there_are_three_parts(self):
        cases = {
            '127.0.0.1:8080:8080': Binding('127.0.0.1', '8080'),
            '8080:80': Binding('', '80'),
            '80': Binding('', '80'),
            '80/tcp': Binding('', '80'),
            '127.0.0.1::80': Binding('127.0.0.1', '80'),
            '[::1]:5432:5432': Binding('[::1]', '5432'),
        }
        for text, binding in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_short(text), binding)

    def test_does_not_split_inside_an_unresolved_variable(self):
        # .env 없이 읽으면 ${PROXY_PORT:-8080} 이 그대로 온다. 그 안의 쌍점에서 나누면 주소를 잘못 읽는다
        self.assertEqual(parse_short('127.0.0.1:${PROXY_PORT:-8080}:8080'), Binding('127.0.0.1', '8080'))

    def test_an_unresolved_address_is_not_loopback(self):
        # 무엇으로 채워질지 모르는 주소는 믿지 않는다
        self.assertEqual(parse_short('${BIND_IP:-127.0.0.1}:80:80').host_ip, '${BIND_IP:-127.0.0.1}')


class CheckTests(unittest.TestCase):
    def test_passes_when_only_listed_services_open_loopback_ports(self):
        services = config(
            proxy={'ports': ['127.0.0.1:${PROXY_PORT:-8080}:8080']},
            db={'ports': [{'host_ip': '127.0.0.1', 'target': 5432, 'published': '5432'}]},
            **{'board-server': {}},
        )

        self.assertEqual(check(services), [])

    def test_a_port_without_an_address_opens_on_every_address(self):
        self.assertEqual(
            check(config(db={'ports': ['5432:5432']})),
            ['db: 5432 을 모든 주소 에 연다. 127.0.0.1 에 묶는다'],
        )

    def test_a_long_form_port_without_an_address_opens_on_every_address(self):
        self.assertEqual(
            check(config(db={'ports': [{'target': 5432, 'published': '5432'}]})),
            ['db: 5432 을 모든 주소 에 연다. 127.0.0.1 에 묶는다'],
        )

    def test_a_server_behind_the_proxy_may_not_open_a_port(self):
        # 서버 넷이 포트를 열면 프록시의 요청 수 제한과 경로 차단을 건너뛴다. 루프백이어도 안 된다
        problems = check(config(**{'billing-server': {'ports': ['127.0.0.1:8003:8003']}}))

        self.assertEqual(len(problems), 1)
        self.assertIn('billing-server: 포트를 연다', problems[0])

    def test_host_networking_is_refused(self):
        problems = check(config(**{'game-server': {'network_mode': 'host'}}))

        self.assertEqual(len(problems), 1)
        self.assertIn('network_mode: host', problems[0])


class PublicPortTests(unittest.TestCase):
    """staging 의 설정(--public)에서만 프록시의 HTTP, HTTPS 를 모든 주소에 연다(#451)."""

    staging_proxy = {'ports': [{'target': 8080, 'published': '80'}, {'target': 8443, 'published': '443'}]}

    def test_the_proxy_may_open_http_and_https_to_everyone_in_staging(self):
        self.assertEqual(check(config(proxy=self.staging_proxy), PUBLIC_PORTS), [])

    def test_the_same_ports_are_refused_in_the_local_config(self):
        # 로컬의 docker-compose.yml 이 모든 주소에 열면 PC 가 같은 와이파이의 기기에 열린다
        problems = check(config(proxy=self.staging_proxy))

        self.assertEqual(len(problems), 2)

    def test_other_proxy_ports_stay_on_loopback_in_staging(self):
        problems = check(config(proxy={'ports': ['8081:8081']}), PUBLIC_PORTS)

        self.assertEqual(problems, ['proxy: 8081 을 모든 주소 에 연다. 127.0.0.1 에 묶는다'])

    def test_other_services_stay_on_loopback_in_staging(self):
        # 같은 포트 번호여도 프록시가 아니면 안 된다
        problems = check(config(grafana={'ports': ['3000:8443']}, db={'ports': ['5432:5432']}), PUBLIC_PORTS)

        self.assertEqual(len(problems), 2)

    def test_only_the_public_flag_opens_them(self):
        self.assertEqual(allowed_public_ports([]), frozenset())
        self.assertEqual(allowed_public_ports(['--public']), PUBLIC_PORTS)
        with self.assertRaises(ValueError):
            allowed_public_ports(['--everything'])


if __name__ == '__main__':
    unittest.main()
