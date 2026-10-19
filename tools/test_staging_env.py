# tools/test_staging_env.py

"""
staging 의 .env 를 만드는 도구(staging_env.py)를 본다. 저장소의 진짜 .env.example 을 빈 폴더에 옮겨 그 위에서 만든다.

    사용: python3 -m unittest discover -s tools -p 'test_staging_env.py'

stack-smoke.sh 의 check-staging 이 부른다. 짝이 어긋나면 VM 에서 서버끼리의 요청이 401 로 조용히 거절된다.
"""

import contextlib
import io
import re
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from staging_env import OPTIONAL_SECRETS, PAIRS, REPO_ROOT, TARGETS, TO_FILL, main, set_value

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
        for target in TARGETS:
            (self.root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO_ROOT / f'{target}.example', self.root / f'{target}.example')

    def run_tool(self, args=ARGS) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(args, root=self.root)

    def env(self, target: str) -> dict[str, str]:
        return read_env(self.root / target)

    def test_writes_all_six_files_for_the_owner_only(self):
        self.assertEqual(self.run_tool(), 0)

        for target in TARGETS:
            mode = stat.S_IMODE((self.root / target).stat().st_mode)
            self.assertEqual(mode, 0o600, target)

    def test_paired_secrets_are_equal_and_long(self):
        self.run_tool()

        for label, places in PAIRS.items():
            values = {self.env(target)[name] for target, name in places}
            self.assertEqual(len(values), 1, label)
            self.assertGreaterEqual(len(values.pop()), 32, label)

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

    def test_database_urls_use_the_root_passwords(self):
        self.run_tool()
        root = self.env('.env')

        self.assertIn(f':{root["AUTH_DB_PASSWORD"]}@db:5432/trpg', self.env('auth-server/.env')['DATABASE_URL'])
        self.assertIn(f':{root["GAME_DB_PASSWORD"]}@db:5432/trpg', self.env('game-server/.env')['DATABASE_URL'])
        self.assertIn(f':{root["BOARD_DB_PASSWORD"]}@db:5432/trpg', self.env('board-server/.env')['DATABASE_URL'])
        self.assertIn(f':{root["BILLING_DB_PASSWORD"]}@db:5432/trpg', self.env('billing-server/.env')['DATABASE_URL'])
        self.assertIn(
            f':{root["NOTIFICATION_DB_PASSWORD"]}@db:5432/trpg', self.env('notification-server/.env')['DATABASE_URL']
        )

    def test_staging_values_are_set(self):
        self.run_tool()
        root = self.env('.env')

        self.assertEqual(root['COMPOSE_FILE'], 'docker-compose.yml:docker-compose.staging.yml')
        self.assertEqual(root['COMPOSE_PROFILES'], 'app,observability')
        self.assertEqual(root['DOMAIN'], 'trpg.example.com')
        self.assertEqual(root['GAME_LLM_BASE_URL'], 'http://100.64.0.2:11434/v1')
        self.assertEqual(root['BACKUP_AGE_RECIPIENTS'], 'age1master age1check')
        self.assertEqual(root['AUTH_DB_ALLOW_TEST_DB'], 'false')
        for target in TARGETS:
            self.assertEqual(self.env(target).get('APP_ENVIRONMENT'), 'staging', target)
        self.assertEqual(self.env('billing-server/.env')['PAYMENT_PROVIDER'], 'fake')
        self.assertEqual(self.env('game-server/.env')['LLM_MODEL'], 'glm-4-7-flash')

    def test_debug_is_off_where_servers_read_it(self):
        self.run_tool()

        for target in ('auth-server/.env', 'game-server/.env', 'billing-server/.env', 'notification-server/.env'):
            self.assertEqual(self.env(target)['DEBUG'], 'false', target)

    def test_no_placeholder_is_left_in_what_it_set(self):
        self.run_tool()

        for target in TARGETS:
            text = (self.root / target).read_text(encoding='utf-8')
            for line in text.splitlines():
                if not line.startswith('#'):
                    self.assertNotIn('여기에', line, target)
                    self.assertNotIn('바꿔야합니다', line, target)

    def test_every_secret_in_the_examples_is_filled(self):
        # 예시에 새 비밀이 생기면(주석으로 막힌 것도) 이 도구가 만들거나, 비워 두어도 되는 것이라고 적어야 한다.
        # 빠뜨리면 VM 에서 그 서버가 뜨지 않거나 서버끼리의 요청이 거절된다
        self.run_tool()
        left_for_a_person = {name for _, name, _ in TO_FILL}
        secret = re.compile(r'^#?[ \t]*([A-Z][A-Z0-9_]*(?:PASSWORD|SECRET|_KEY))=', re.MULTILINE)

        for target in TARGETS:
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


class SetValueTests(unittest.TestCase):
    def test_replaces_the_first_uncommented_line(self):
        self.assertEqual(set_value('A=1\n# A=2 설명\n', 'A', 'x'), 'A=x\n# A=2 설명\n')

    def test_uncomments_when_only_a_commented_line_exists(self):
        self.assertEqual(set_value('# 설명\n# A=\n', 'A', 'x'), '# 설명\nA=x\n')

    def test_does_not_touch_a_longer_name(self):
        self.assertEqual(set_value('AB=1\nA=2\n', 'A', 'x'), 'AB=1\nA=x\n')

    def test_appends_a_name_that_is_not_in_the_example(self):
        text = set_value('A=1\n', 'B', 'x')

        self.assertTrue(text.endswith('B=x\n'))
        self.assertIn('tools/staging_env.py 가 더한 값', text)

    def test_keeps_backslashes_in_the_value(self):
        self.assertEqual(set_value('A=\n', 'A', r'a\1b'), 'A=a\\1b\n')


if __name__ == '__main__':
    unittest.main()
