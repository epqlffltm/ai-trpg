# tools/test_staging_env.py

"""
staging 의 .env 를 만드는 도구(staging_env.py)를 본다. 저장소의 진짜 .env.example 을 빈 폴더에 옮겨 그 위에서 만든다.
비밀을 채우는 규칙 자체는 tools/test_fill_env.py 가 본다.
여기서는 staging 에서 그 비밀이 모두(한 파일만 아는 것까지) 켜져 있고 짝이 맞는지를 본다.

    사용: python3 -m unittest discover -s tools -p 'test_staging_env.py'

stack-smoke.sh 의 check-staging 이 부른다.
짝이 어긋나거나 한쪽이 주석이면 VM 에서 서버끼리의 요청이 401 로 조용히 거절된다.
"""

import contextlib
import io
import os
import re
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from fill_env import ENV_FILES, SECRETS
from staging_env import OPTIONAL_SECRETS, REPO_ROOT, TO_FILL, enable, main, set_value

ARGS = [
    '--domain',
    'trpg.example.com',
    '--acme-email',
    'ops@example.com',
    '--llm-base-url',
    'http://100.64.0.2:11434/v1',
    '--s3-bucket',
    'ai-trpg-backups',
    '--age-recipients',
    'age1master age1check',
]


def read_env(path: Path) -> dict[str, str]:
    """주석이 아닌 "이름=값" 줄들. 같은 이름이 둘이면 실패한다(서버가 어느 쪽을 읽을지 모른다)."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        match = re.match(r'^([A-Z][A-Z0-9_]*)=(.*)$', line)
        if match:
            name, value = match.groups()
            if name in values:
                raise AssertionError(f'{path.name} 에 {name} 이 둘이다')
            values[name] = value
    return values


class StagingEnvTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for target in ENV_FILES:
            (self.root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO_ROOT / f'{target}.example', self.root / f'{target}.example')

    def run_tool(self, args=ARGS) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(args, root=self.root)

    def env(self, target: str) -> dict[str, str]:
        return read_env(self.root / target)

    # Windows 에는 리눅스의 파일 권한이 없어 늘 666 으로 읽힌다. VM(리눅스)과 CI 에서만 본다
    @unittest.skipUnless(os.name == 'posix', '파일 권한(600)은 리눅스에서만 뜻이 있다')
    def test_writes_all_six_files_for_the_owner_only(self):
        self.assertEqual(self.run_tool(), 0)

        for target in ENV_FILES:
            mode = stat.S_IMODE((self.root / target).stat().st_mode)
            self.assertEqual(mode, 0o600, target)

    def test_every_secret_of_fill_env_is_enabled_and_paired(self):
        # 주석인 채로 남으면 그 서버는 비밀 없이 뜨고, 짝인 서버는 그 요청을 거절한다
        self.run_tool()

        for secret in SECRETS:
            lines = [spot for spot in secret.spots if not spot.url]
            with self.subTest(secret=secret.name):
                values = {self.env(spot.file).get(spot.key) for spot in lines}
                self.assertEqual(len(values), 1)
                value = values.pop()
                self.assertIsNotNone(value, '켜져 있지 않다')
                self.assertGreaterEqual(len(value), 32)

    def test_database_passwords_are_in_the_root_env(self):
        # 서버의 DATABASE_URL 은 compose 가 루트 .env 의 비밀번호로 만든다(docker-compose.yml)
        self.run_tool()
        root = self.env('.env')

        for name in ('POSTGRES_PASSWORD', 'AUTH_DB_PASSWORD', 'GAME_DB_PASSWORD', 'BOARD_DB_PASSWORD'):
            self.assertGreaterEqual(len(root[name]), 32, name)
        for name in ('BILLING_DB_PASSWORD', 'NOTIFICATION_DB_PASSWORD', 'MONITOR_DB_PASSWORD'):
            self.assertGreaterEqual(len(root[name]), 32, name)

    def test_every_secret_is_different_from_the_others(self):
        # 짝이 아닌 비밀끼리 같으면 하나가 새면 다른 것도 열린다. 알림 서버는 넣는 서버마다 다른 비밀을 요구한다
        self.run_tool()
        notification = self.env('notification-server/.env')

        secrets = [
            notification['GAME_SERVER_SECRET'],
            notification['BILLING_SERVER_SECRET'],
            notification['BOARD_SERVER_SECRET'],
            self.env('auth-server/.env')['SECRET_KEY'],
            self.env('auth-server/.env')['BILLING_SECRET'],
            self.env('game-server/.env')['BILLING_SECRET'],
            self.env('game-server/.env')['SIGNAL_SECRET'],
            self.env('game-server/.env')['AI_LOG_HMAC_KEY'],
            self.env('billing-server/.env')['PG_WEBHOOK_SECRET'],
            self.env('.env')['POSTGRES_PASSWORD'],
            self.env('.env')['GRAFANA_ADMIN_PASSWORD'],
            self.env('.env')['MONITOR_DB_PASSWORD'],
        ]
        self.assertEqual(len(set(secrets)), len(secrets))

    def test_staging_values_are_set(self):
        self.run_tool()
        root = self.env('.env')

        self.assertEqual(root['COMPOSE_FILE'], 'docker-compose.yml:docker-compose.staging.yml')
        self.assertEqual(root['COMPOSE_PROFILES'], 'app,observability')
        self.assertEqual(root['APP_ENVIRONMENT'], 'staging')
        self.assertEqual(root['DOMAIN'], 'trpg.example.com')
        self.assertEqual(root['ACME_EMAIL'], 'ops@example.com')
        self.assertEqual(root['GAME_LLM_BASE_URL'], 'http://100.64.0.2:11434/v1')
        self.assertEqual(root['OTEL_EXPORTER_OTLP_ENDPOINT'], 'http://alloy:4318')
        self.assertEqual(root['BACKUP_S3_BUCKET'], 'ai-trpg-backups')
        self.assertEqual(root['BACKUP_S3_REGION'], 'ap-northeast-2')
        self.assertEqual(root['BACKUP_AGE_RECIPIENTS'], 'age1master age1check')
        self.assertEqual(root['AUTH_DB_ALLOW_TEST_DB'], 'false')
        self.assertEqual(self.env('billing-server/.env')['PAYMENT_PROVIDER'], 'fake')
        self.assertEqual(self.env('game-server/.env')['NARRATOR'], 'llm')
        self.assertEqual(self.env('game-server/.env')['LLM_MODEL'], 'glm-4-7-flash')

    def test_staging_lines_of_the_root_example_are_the_ones_enabled(self):
        # 루트 예시는 로컬용 줄(# GAME_LLM_BASE_URL=http://host.docker.internal...) 뒤에 staging 용 줄을 둔다.
        # staging 의 설명 아래 줄이 켜져야 사람이 읽을 때 헷갈리지 않는다
        self.run_tool()
        text = (self.root / '.env').read_text(encoding='utf-8')

        self.assertIn('# GAME_LLM_BASE_URL=http://host.docker.internal', text)
        self.assertIn('# APP_ENVIRONMENT=development', text)

    def test_no_placeholder_is_left(self):
        self.run_tool()

        for target in ENV_FILES:
            text = (self.root / target).read_text(encoding='utf-8')
            for line in text.splitlines():
                if not line.startswith('#'):
                    self.assertNotIn('여기에', line, target)
                    self.assertNotIn('바꿔야합니다', line, target)

    def test_every_secret_in_the_examples_is_filled(self):
        # 예시에 새 비밀이 생기면(주석으로 막힌 것도) fill_env.py 의 표에 넣거나, 비워 두어도 되는 것이라고 적어야 한다.
        # 빠뜨리면 VM 에서 그 서버가 뜨지 않거나 서버끼리의 요청이 거절된다
        self.run_tool()
        left_for_a_person = {name for _, name, _ in TO_FILL}
        secret = re.compile(r'^#?[ \t]*([A-Z][A-Z0-9_]*(?:PASSWORD|SECRET|_KEY))=', re.MULTILINE)

        for target in ENV_FILES:
            example = (self.root / f'{target}.example').read_text(encoding='utf-8')
            written = self.env(target)
            for name in set(secret.findall(example)) - OPTIONAL_SECRETS - left_for_a_person:
                with self.subTest(target=target, name=name):
                    self.assertTrue(written.get(name), f'{target} 의 {name} 를 채우지 않았다')

    def test_keys_left_for_a_person_are_empty(self):
        # 비워 두면 compose 가 S3 의 키 없이 뜨기를 거부한다(${...:?})
        self.run_tool()

        self.assertEqual(self.env('.env')['BACKUP_AWS_ACCESS_KEY_ID'], '')
        self.assertEqual(self.env('.env')['BACKUP_AWS_SECRET_ACCESS_KEY'], '')
        self.assertEqual(self.env('game-server/.env')['ZAI_API_KEY'], '')

    def test_refuses_and_writes_nothing_when_one_file_exists(self):
        (self.root / 'board-server/.env').write_text('LEFT=alone\n', encoding='utf-8')

        self.assertEqual(self.run_tool(), 1)

        self.assertFalse((self.root / '.env').exists())
        self.assertEqual((self.root / 'board-server/.env').read_text(encoding='utf-8'), 'LEFT=alone\n')

    def test_two_age_recipients_are_required(self):
        with self.assertRaises(SystemExit):
            self.run_tool([*ARGS[:-1], 'age1only'])


class EnableTests(unittest.TestCase):
    def test_uncomments_keeping_the_value(self):
        lines = ['# 설명\n', '# A=abc\n']
        enable(lines, 'A')

        self.assertEqual(lines, ['# 설명\n', 'A=abc\n'])

    def test_leaves_an_enabled_line_alone(self):
        lines = ['A=1\n', '# A=2\n']
        enable(lines, 'A')

        self.assertEqual(lines, ['A=1\n', '# A=2\n'])

    def test_uncomments_the_first_commented_line_where_fill_env_wrote(self):
        lines = ['# A=filled\n', '# A=\n']
        enable(lines, 'A')

        self.assertEqual(lines, ['A=filled\n', '# A=\n'])


class SetValueTests(unittest.TestCase):
    def test_replaces_the_uncommented_line(self):
        lines = ['A=1\n', '# A=2 설명\n']
        set_value(lines, 'A', 'x')

        self.assertEqual(lines, ['A=x\n', '# A=2 설명\n'])

    def test_uncomments_the_last_commented_line(self):
        lines = ['# A=local\n', '# --- staging ---\n', '# A=\n']
        set_value(lines, 'A', 'x')

        self.assertEqual(lines, ['# A=local\n', '# --- staging ---\n', 'A=x\n'])

    def test_does_not_touch_a_longer_name(self):
        lines = ['AB=1\n', 'A=2\n']
        set_value(lines, 'A', 'x')

        self.assertEqual(lines, ['AB=1\n', 'A=x\n'])

    def test_appends_a_name_that_is_not_in_the_example(self):
        lines = ['A=1']
        set_value(lines, 'B', 'x')

        self.assertEqual(lines[0], 'A=1\n')
        self.assertEqual(lines[-1], 'B=x\n')
        self.assertIn('tools/staging_env.py 가 더한 값', ''.join(lines))

    def test_keeps_crlf(self):
        lines = ['A=1\r\n']
        set_value(lines, 'A', 'x')

        self.assertEqual(lines, ['A=x\r\n'])


if __name__ == '__main__':
    unittest.main()
