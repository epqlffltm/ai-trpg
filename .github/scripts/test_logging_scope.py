# .github/scripts/test_logging_scope.py

"""
로그 상한의 검사(logging_scope.py)의 규칙을 본다. compose 없이, 작은 설정을 만들어 넣는다.

    사용: python3 -m unittest discover -s .github/scripts -p 'test_*_scope.py'

stack-smoke.sh 의 check 가 실제 설정을 검사하기 전에 부른다. 규칙이 틀리면 상한 없는 서비스를 놓치고 초록이 된다.
"""

import unittest

from logging_scope import check

# docker-compose.yml 의 x-logging 과 같은 모양
LIMITED = {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '5'}}


def config(**services: dict) -> dict:
    return {'services': services}


class CheckTests(unittest.TestCase):
    def test_passes_when_every_service_has_limits(self):
        services = config(db={'logging': LIMITED}, **{'board-server': {'logging': LIMITED}})

        self.assertEqual(check(services), [])

    def test_a_service_without_logging_is_caught(self):
        # 적지 않으면 VM 의 기본(대개 상한 없는 json-file)을 따른다
        self.assertEqual(
            check(config(redis={})),
            ['redis: 로그 설정이 없다. logging: *logging 을 붙인다'],
        )

    def test_both_limits_are_required(self):
        # max-file 은 max-size 가 없으면 뜻이 없다.
        # max-size 만 두면 파일 수가 기본(1)이라 지난 로그가 바로 지워진다. 둘 다 적는다
        only_size = {'driver': 'json-file', 'options': {'max-size': '10m'}}
        only_files = {'driver': 'json-file', 'options': {'max-file': '5'}}

        self.assertEqual(
            check(config(proxy={'logging': only_size}, db={'logging': only_files})),
            [
                'db: 로그에 max-size 가 없다. logging: *logging 을 붙인다',
                'proxy: 로그에 max-file 가 없다. logging: *logging 을 붙인다',
            ],
        )

    def test_an_empty_limit_does_not_count(self):
        empty = {'driver': 'json-file', 'options': {'max-size': '', 'max-file': '5'}}

        self.assertEqual(len(check(config(db={'logging': empty}))), 1)

    def test_another_driver_is_caught(self):
        # 다른 드라이버는 docker logs 가 되지 않거나(none, syslog) 수집기가 읽는 길이 다르다
        problems = check(config(db={'logging': {'driver': 'none'}}))

        self.assertEqual(problems, ['db: 로그 드라이버가 none 이다. json-file 여야 한다. logging: *logging 을 붙인다'])


if __name__ == '__main__':
    unittest.main()
