# .github/scripts/test_secret_scope.py

"""
비밀의 범위 검사(secret_scope.py)의 규칙을 본다. compose 없이, 작은 설정을 만들어 넣는다.

    사용: python3 -m unittest discover -s .github/scripts -p 'test_secret_scope.py'

stack-smoke.sh 의 check 가 실제 설정을 검사하기 전에 부른다. 규칙이 틀리면 새는 비밀을 놓치고 초록이 된다.
"""

import tempfile
import unittest
from pathlib import Path

from secret_scope import SECRETS, Secret, check

TABLE = [
    Secret('auth-server', 'BILLING_SECRET', frozenset({'auth-welcome-credits'})),
    Secret('auth-server', 'SECRET_KEY', frozenset({'auth-server', 'auth-mail'})),
]
KEYS = {'type': 'bind', 'source': '/repo/auth-server/keys', 'target': '/app/keys'}


def service(environment: dict | None = None, volumes: list | None = None, server: str = 'auth-server') -> dict:
    """서버 폴더의 .env 를 통째로 받는 프로세스 하나."""
    return {
        'env_file': [{'path': f'/repo/{server}/.env', 'required': True}],
        'environment': environment or {},
        'volumes': volumes or [],
    }


def without_key(**environment: str) -> dict:
    """서명 키를 받지 않는 인증 프로세스. 키의 경로를 비웠다."""
    return {'JWT_PRIVATE_KEY_PATH': '', **environment}


class SecretScopeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def problems(self, services: dict) -> list[str]:
        return check({'services': services}, self.root, TABLE)

    def test_passes_when_each_secret_goes_only_where_it_is_used(self):
        services = {
            'auth-server': service({'JWT_PRIVATE_KEY_PATH': 'keys/jwt-private.pem', 'BILLING_SECRET': ''}, [KEYS]),
            'auth-mail': service(without_key(BILLING_SECRET='')),
            'auth-welcome-credits': service(without_key(SECRET_KEY='')),
        }

        self.assertEqual(self.problems(services), [])

    def test_a_secret_that_is_not_blanked_leaks(self):
        # 덮지 않으면 .env 의 값이 그대로 간다. 값이 무엇인지는 보지 않는다
        services = {'auth-mail': service(without_key())}

        self.assertEqual(
            self.problems(services), ['auth-mail: BILLING_SECRET 를 받는다. environment 에서 빈 값으로 덮는다']
        )

    def test_a_secret_from_another_server_does_not_count(self):
        # 게임 서버의 .env 에는 인증 서버의 BILLING_SECRET 이 없다. 같은 이름이라도 서버마다 따로 본다
        services = {'game-migrate': service(server='game-server')}

        self.assertEqual(self.problems(services), [])

    def test_only_the_auth_server_mounts_the_signing_key(self):
        services = {'auth-mail': service(without_key(BILLING_SECRET=''), [KEYS])}

        self.assertEqual(self.problems(services), ['auth-mail: 서명 개인키의 폴더(auth-server/keys)를 붙였다'])

    def test_other_auth_processes_blank_the_key_path(self):
        # 경로가 남으면 설정이 키를 찾다가 뜨지 않는다. 비운 것만 키 없이 뜬다
        services = {'auth-mail': service({'BILLING_SECRET': ''})}

        self.assertEqual(self.problems(services), ['auth-mail: JWT_PRIVATE_KEY_PATH 를 비우지 않았다'])

    def test_reads_the_environment_as_a_list_too(self):
        # 파일을 둘 겹치면(docker-compose.staging.yml) compose 가 environment 를 "이름=값"의 목록으로 낸다
        services = {
            'auth-mail': {**service(), 'environment': ['JWT_PRIVATE_KEY_PATH=', 'BILLING_SECRET=', 'DEBUG=false']},
            'auth-cron': {
                **service(),
                'environment': ['JWT_PRIVATE_KEY_PATH=', 'SECRET_KEY=', 'APP_ENVIRONMENT=staging'],
            },
        }

        self.assertEqual(
            self.problems(services), ['auth-cron: BILLING_SECRET 를 받는다. environment 에서 빈 값으로 덮는다']
        )

    def test_a_name_without_a_value_in_the_list_is_not_blanked(self):
        # "BILLING_SECRET" 만 적은 줄은 compose 를 띄운 셸의 값을 넘긴다. 비운 것이 아니다
        services = {'auth-mail': {**service(), 'environment': ['JWT_PRIVATE_KEY_PATH=', 'BILLING_SECRET']}}

        self.assertEqual(
            self.problems(services), ['auth-mail: BILLING_SECRET 를 받는다. environment 에서 빈 값으로 덮는다']
        )

    def test_a_new_secret_in_an_example_must_be_listed(self):
        server = self.root / 'auth-server'
        server.mkdir()
        (server / '.env.example').write_text(
            'SECRET_KEY=\n# BILLING_SECRET=\n# NEW_PROVIDER_API_KEY=\n# PASSWORD_RESET_URL=http://x\nDEBUG=true\n',
            encoding='utf-8',
        )

        self.assertEqual(
            self.problems({}),
            ['auth-server/.env.example 의 NEW_PROVIDER_API_KEY 가 표에 없다. secret_scope.py 의 SECRETS 에 적는다'],
        )


# 루트 .env 의 비밀의 작은 표. DB 와 수집기만 monitor 의 비밀번호를 받는다
ROOT_TABLE = {
    'POSTGRES_PASSWORD': frozenset({'db'}),
    'MONITOR_DB_PASSWORD': frozenset({'db', 'alloy'}),
}


def using(**environment: str) -> dict:
    """루트 .env 를 environment 의 값으로 부르는 프로세스 하나. .env 를 통째로 받지 않는다."""
    return {'environment': environment}


class RootSecretScopeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def problems(self, services: dict) -> list[str]:
        return check({'services': services}, self.root, [], ROOT_TABLE)

    def test_passes_when_root_secrets_go_only_where_they_are_used(self):
        services = {
            'db': using(
                POSTGRES_PASSWORD='${POSTGRES_PASSWORD:?설정하세요}', MONITOR_DB_PASSWORD='${MONITOR_DB_PASSWORD:-}'
            ),
            'alloy': using(MONITOR_DB_PASSWORD='${MONITOR_DB_PASSWORD:-}', COMPOSE_PROJECT='${COMPOSE_PROJECT_NAME}'),
        }

        self.assertEqual(self.problems(services), [])

    def test_a_root_secret_inside_another_value_counts(self):
        # 주소 안에 비밀번호를 넣어 넘겨도 받은 것이다
        services = {'grafana': using(GF_DATABASE_URL='postgres://monitor:${MONITOR_DB_PASSWORD}@db/trpg')}

        self.assertEqual(
            self.problems(services), ['grafana: 루트 .env 의 MONITOR_DB_PASSWORD 를 받는다. 받을 프로세스가 아니다']
        )

    def test_a_root_secret_missing_from_the_table_is_reported(self):
        services = {'alloy': using(TOKEN='${NEW_EXPORTER_API_KEY:-}')}

        self.assertEqual(
            self.problems(services),
            ['alloy: 루트 .env 의 NEW_EXPORTER_API_KEY 를 받는데 표에 없다. secret_scope.py 의 ROOT_SECRETS 에 적는다'],
        )

    def test_settings_that_are_not_secrets_are_not_counted(self):
        services = {'alloy': using(MONITOR_DB_NAME='${POSTGRES_DB:-trpg}', PORT='${GRAFANA_PORT:-3000}')}

        self.assertEqual(self.problems(services), [])

    def test_a_new_secret_in_the_root_example_must_be_listed(self):
        (self.root / '.env.example').write_text(
            'POSTGRES_PASSWORD=\nMONITOR_DB_PASSWORD=\n# REDIS_PASSWORD=\nPOSTGRES_PORT=5432\n', encoding='utf-8'
        )

        self.assertEqual(
            self.problems({}),
            ['.env.example 의 REDIS_PASSWORD 가 표에 없다. secret_scope.py 의 ROOT_SECRETS 에 적는다'],
        )

    def test_the_repository_root_example_is_fully_listed(self):
        repository = Path(__file__).resolve().parents[2]

        self.assertEqual(check({'services': {}}, repository, SECRETS), [])


if __name__ == '__main__':
    unittest.main()
