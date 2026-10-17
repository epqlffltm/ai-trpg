# .github/scripts/test_port_scope.py

"""
열린 포트의 검사(port_scope.py)의 규칙을 본다. compose 없이, 작은 설정을 만들어 넣는다.

    사용: python3 -m unittest discover -s .github/scripts -p 'test_*_scope.py'

stack-smoke.sh 의 check 가 실제 설정을 검사하기 전에 부른다. 규칙이 틀리면 열린 포트를 놓치고 초록이 된다.
"""

import unittest

from port_scope import Binding, check, parse_short


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


if __name__ == '__main__':
    unittest.main()
