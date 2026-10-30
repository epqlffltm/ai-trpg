# tools/test_fill_env.py

"""
.env 를 만들고 비밀을 채우는 스크립트(fill_env.py)를 본다. 임시 폴더에 작은 .env.example 들을 만들어 넣는다.

    사용: python3 -m unittest discover -s tools -p 'test_*.py'

stack-smoke.sh 의 check 가 설정 검사의 규칙과 함께 부른다.
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import fill_env
from fill_env import ENV_FILES, PLACEHOLDERS, main, run

# 서버마다의 작은 .env.example. 저장소의 것과 같은 모양(빈 값, 자리표시자, 주석으로 막은 줄)이다
EXAMPLES = {
    '.env': 'POSTGRES_USER=trpg\nPOSTGRES_PASSWORD=\nAUTH_DB_PASSWORD=\nGAME_DB_PASSWORD=\nBOARD_DB_PASSWORD=\n'
    'BILLING_DB_PASSWORD=\nNOTIFICATION_DB_PASSWORD=\nASSET_DB_PASSWORD=\nCHAT_DB_PASSWORD=\nSTORY_DB_PASSWORD=\n'
    'GRAFANA_ADMIN_PASSWORD=\nMONITOR_DB_PASSWORD=\n'
    '# BACKUP_AWS_SECRET_ACCESS_KEY=\n# ALERT_SLACK_WEBHOOK_URL=\n'
    '# ALERT_TELEGRAM_BOT_TOKEN=\n# ALERT_TELEGRAM_CHAT_ID=\n',
    'auth-server/.env': 'SECRET_KEY=\nDATABASE_URL=postgres://auth:여기에_비밀번호@127.0.0.1:5432/trpg\n'
    '# SMTP_PASSWORD=\n# BILLING_SECRET=\n# ASSET_SECRET=\n# GAME_SECRET=\n# NOTIFICATION_SECRET=\n# BOARD_SECRET=\n'
    '# CHAT_SECRET=\n# STORY_SECRET=\n'
    '# PASSWORD_RESET_URL=http://localhost:5173/reset-password\n',
    'trpg-server/.env': 'DATABASE_URL=postgresql+asyncpg://game:여기에비밀번호@127.0.0.1:5432/trpg\n'
    '# SIGNAL_SECRET=\n# AI_LOG_HMAC_KEY=\n# BILLING_SECRET=\n# NOTIFICATION_SECRET=\n# OPENAI_API_KEY=\n'
    'AUTH_SERVER_SECRET=\n',
    'board-server/.env': 'DATABASE_URL=postgresql://board:여기에비밀번호@127.0.0.1:5432/trpg\n'
    '# NOTIFICATION_SECRET=\n# AUTH_SERVER_SECRET=\n',
    'billing-server/.env': 'DATABASE_URL=postgres://billing:여기에비밀번호@127.0.0.1:5432/trpg\n'
    'PG_WEBHOOK_SECRET=바꿔야합니다\nGAME_SERVER_SECRET=바꿔야합니다\nAUTH_SERVER_SECRET=바꿔야합니다\n'
    '# CHAT_SERVER_SECRET=\n# STORY_SERVER_SECRET=\n# NOTIFICATION_SECRET=\n# TOSS_SECRET_KEY=\n',
    'notification-server/.env': 'DATABASE_URL=postgresql+asyncpg://notification:여기에비밀번호@127.0.0.1:5432/trpg\n'
    'GAME_SERVER_SECRET=\nBILLING_SERVER_SECRET=\nBOARD_SERVER_SECRET=\nSTORY_SERVER_SECRET=\nAUTH_SERVER_SECRET=\n',
    'asset-server/.env': 'DATABASE_URL=postgresql+asyncpg://asset:여기에비밀번호@127.0.0.1:5432/trpg\n'
    'CHAT_SERVER_SECRET=\nSTORY_SERVER_SECRET=\nAUTH_SERVER_SECRET=\n',
    'chat-server/.env': 'DATABASE_URL=postgresql+asyncpg://chat:여기에비밀번호@127.0.0.1:5432/trpg\n'
    '# ASSET_URL=http://127.0.0.1:8006\n# ASSET_SECRET=\n# BILLING_URL=http://127.0.0.1:8003\n# BILLING_SECRET=\n'
    '# AUTH_SERVER_SECRET=\n',
    'story-server/.env': 'DATABASE_URL=postgresql+asyncpg://story:여기에비밀번호@127.0.0.1:5432/trpg\n'
    'ASSET_URL=http://127.0.0.1:8006\n# ASSET_SECRET=\n# BILLING_URL=http://127.0.0.1:8003\n# BILLING_SECRET=\n'
    '# AUTH_SERVER_SECRET=\n# NOTIFICATION_SECRET=\n',
}


def values(text: str) -> dict[str, str]:
    """.env 의 이름과 값. 주석으로 막은 줄도 넣는다(이름 앞에 # 를 붙인다)."""
    pairs = {}
    for line in text.splitlines():
        if '=' not in line:
            continue
        name, _, value = line.partition('=')
        pairs[name.replace('# ', '#')] = value
    return pairs


def password(url: str) -> str:
    """접속 주소의 비밀번호 부분."""
    return url.split('://', 1)[1].split('@', 1)[0].split(':', 1)[1]


class FillEnvTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for relative, text in EXAMPLES.items():
            example = (self.root / relative).with_name('.env.example')
            example.parent.mkdir(parents=True, exist_ok=True)
            example.write_text(text, encoding='utf-8')

    def env(self, relative: str) -> dict[str, str]:
        return values((self.root / relative).read_text(encoding='utf-8'))

    def fill(self, dry_run: bool = False):
        return run(self.root, dry_run)

    def test_creates_every_env_file_from_its_example(self):
        self.fill()

        for relative in ENV_FILES:
            self.assertTrue((self.root / relative).exists(), relative)

    def test_every_listed_secret_is_filled_with_a_long_random_value(self):
        self.fill()

        root = self.env('.env')
        for name in ('POSTGRES_PASSWORD', 'AUTH_DB_PASSWORD', 'MONITOR_DB_PASSWORD', 'GRAFANA_ADMIN_PASSWORD'):
            self.assertEqual(len(root[name]), 64, name)
            self.assertRegex(root[name], r'^[0-9a-f]+$', name)
        self.assertEqual(len(self.env('auth-server/.env')['SECRET_KEY']), 64)
        self.assertNotIn(self.env('billing-server/.env')['PG_WEBHOOK_SECRET'], PLACEHOLDERS)

    def test_different_secrets_get_different_values(self):
        self.fill()

        root = self.env('.env')
        self.assertNotEqual(root['POSTGRES_PASSWORD'], root['AUTH_DB_PASSWORD'])

    def test_database_passwords_match_the_server_urls(self):
        self.fill()

        root = self.env('.env')
        for folder, key in (
            ('auth-server', 'AUTH_DB_PASSWORD'),
            ('trpg-server', 'GAME_DB_PASSWORD'),
            ('billing-server', 'BILLING_DB_PASSWORD'),
            ('story-server', 'STORY_DB_PASSWORD'),
        ):
            url = self.env(f'{folder}/.env')['DATABASE_URL']
            self.assertEqual(password(url), root[key], folder)
            # 주소의 나머지는 그대로다
            self.assertTrue(url.endswith('@127.0.0.1:5432/trpg'), url)

    def test_secrets_two_servers_share_are_the_same(self):
        self.fill()

        auth, game, board = self.env('auth-server/.env'), self.env('trpg-server/.env'), self.env('board-server/.env')
        billing, notification = self.env('billing-server/.env'), self.env('notification-server/.env')
        chat, asset, story = self.env('chat-server/.env'), self.env('asset-server/.env'), self.env('story-server/.env')
        self.assertEqual(auth['BILLING_SECRET'], billing['AUTH_SERVER_SECRET'])
        self.assertEqual(game['BILLING_SECRET'], billing['GAME_SERVER_SECRET'])
        self.assertEqual(game['NOTIFICATION_SECRET'], notification['GAME_SERVER_SECRET'])
        self.assertEqual(billing['NOTIFICATION_SECRET'], notification['BILLING_SERVER_SECRET'])
        self.assertEqual(board['NOTIFICATION_SECRET'], notification['BOARD_SERVER_SECRET'])
        self.assertEqual(story['NOTIFICATION_SECRET'], notification['STORY_SERVER_SECRET'])
        self.assertEqual(chat['ASSET_SECRET'], asset['CHAT_SERVER_SECRET'])
        self.assertEqual(story['ASSET_SECRET'], asset['STORY_SERVER_SECRET'])
        self.assertNotEqual(asset['CHAT_SERVER_SECRET'], asset['STORY_SERVER_SECRET'])
        self.assertEqual(chat['BILLING_SECRET'], billing['CHAT_SERVER_SECRET'])
        self.assertEqual(story['BILLING_SECRET'], billing['STORY_SERVER_SECRET'])
        self.assertNotEqual(billing['CHAT_SERVER_SECRET'], billing['STORY_SERVER_SECRET'])
        self.assertEqual(auth['ASSET_SECRET'], asset['AUTH_SERVER_SECRET'])
        self.assertEqual(auth['GAME_SECRET'], game['AUTH_SERVER_SECRET'])
        self.assertEqual(auth['NOTIFICATION_SECRET'], notification['AUTH_SERVER_SECRET'])
        self.assertEqual(auth['BOARD_SECRET'], board['AUTH_SERVER_SECRET'])
        self.assertEqual(auth['CHAT_SECRET'], chat['AUTH_SERVER_SECRET'])
        self.assertEqual(auth['STORY_SECRET'], story['AUTH_SERVER_SECRET'])
        self.assertNotEqual(auth['CHAT_SECRET'], auth['STORY_SECRET'])

    def test_both_sides_of_a_pair_are_uncommented(self):
        # compose 가 주소(BILLING_URL, NOTIFICATION_URL)를 주므로 비밀이 막혀 있으면 서버가 뜨지 않는다
        self.fill()

        for relative, key in (
            ('auth-server/.env', 'BILLING_SECRET'),
            ('trpg-server/.env', 'BILLING_SECRET'),
            ('trpg-server/.env', 'NOTIFICATION_SECRET'),
            ('board-server/.env', 'NOTIFICATION_SECRET'),
            ('billing-server/.env', 'NOTIFICATION_SECRET'),
            ('chat-server/.env', 'ASSET_SECRET'),
            ('chat-server/.env', 'BILLING_SECRET'),
            ('billing-server/.env', 'CHAT_SERVER_SECRET'),
            ('auth-server/.env', 'ASSET_SECRET'),
            ('auth-server/.env', 'GAME_SECRET'),
            ('auth-server/.env', 'NOTIFICATION_SECRET'),
            ('auth-server/.env', 'BOARD_SECRET'),
            ('board-server/.env', 'AUTH_SERVER_SECRET'),
            ('auth-server/.env', 'CHAT_SECRET'),
            ('chat-server/.env', 'AUTH_SERVER_SECRET'),
            ('story-server/.env', 'ASSET_SECRET'),
            ('story-server/.env', 'BILLING_SECRET'),
            ('billing-server/.env', 'STORY_SERVER_SECRET'),
            ('auth-server/.env', 'STORY_SECRET'),
            ('story-server/.env', 'AUTH_SERVER_SECRET'),
            ('story-server/.env', 'NOTIFICATION_SECRET'),
        ):
            env = self.env(relative)
            self.assertNotIn(f'#{key}', env, relative)
            self.assertEqual(len(env[key]), 64, relative)

    def test_a_filled_but_commented_pair_is_uncommented_later(self):
        # 앞의 판이 주석인 채로 채워 둔 .env 다. 값은 그대로 두고 주석만 푼다
        shared = 'b' * 64
        (self.root / 'trpg-server/.env').write_text(
            f'DATABASE_URL=postgresql+asyncpg://game:pw@db/trpg\n# BILLING_SECRET={shared}\n', encoding='utf-8'
        )
        (self.root / 'billing-server/.env').write_text(f'GAME_SERVER_SECRET={shared}\n', encoding='utf-8')

        _, outcomes, _ = self.fill()

        self.assertEqual(self.env('trpg-server/.env')['BILLING_SECRET'], shared)
        action = next(o.action for o in outcomes if o.name == '게임 서버 → 결제 서버')
        self.assertIn('주석을 풀었다: trpg-server/.env 의 BILLING_SECRET', action)

    def test_a_pair_with_two_different_values_stays_commented(self):
        (self.root / 'trpg-server/.env').write_text('# BILLING_SECRET=one\n', encoding='utf-8')
        (self.root / 'billing-server/.env').write_text('GAME_SERVER_SECRET=two\n', encoding='utf-8')

        self.fill()

        self.assertEqual(self.env('trpg-server/.env')['#BILLING_SECRET'], 'one')

    def test_commented_lines_stay_commented(self):
        # 한 파일만 아는 비밀은 값만 채운다. 켜면 동작이 바뀐다. 켜는 것은 사람이 # 를 지울 때다
        self.fill()

        game = self.env('trpg-server/.env')
        self.assertNotIn('SIGNAL_SECRET', game)
        self.assertEqual(len(game['#SIGNAL_SECRET']), 64)

    def test_keys_from_outside_are_left_empty_and_reported(self):
        _, _, external = self.fill()

        self.assertEqual(self.env('trpg-server/.env')['#OPENAI_API_KEY'], '')
        self.assertEqual(self.env('billing-server/.env')['#TOSS_SECRET_KEY'], '')
        self.assertIn('trpg-server/.env 의 OPENAI_API_KEY', external)
        self.assertIn('.env 의 BACKUP_AWS_SECRET_ACCESS_KEY', external)
        self.assertIn('.env 의 ALERT_SLACK_WEBHOOK_URL', external)
        self.assertIn('.env 의 ALERT_TELEGRAM_BOT_TOKEN', external)
        self.assertNotIn('.env 의 ALERT_TELEGRAM_CHAT_ID', external)
        self.assertEqual(self.env('.env')['#ALERT_TELEGRAM_BOT_TOKEN'], '')
        # 비밀처럼 보이는 이름이지만 주소다
        self.assertNotIn('auth-server/.env 의 PASSWORD_RESET_URL', external)

    def test_values_already_written_are_kept(self):
        (self.root / '.env').write_text('POSTGRES_PASSWORD=mine\nAUTH_DB_PASSWORD=\n', encoding='utf-8')

        self.fill()

        self.assertEqual(self.env('.env')['POSTGRES_PASSWORD'], 'mine')

    def test_one_side_of_a_pair_is_copied_to_the_other(self):
        auth = EXAMPLES['auth-server/.env'].replace('# BILLING_SECRET=', 'BILLING_SECRET=from-auth')
        (self.root / 'auth-server/.env').write_text(auth, encoding='utf-8')

        _, outcomes, _ = self.fill()

        self.assertEqual(self.env('billing-server/.env')['AUTH_SERVER_SECRET'], 'from-auth')
        self.assertIn('맞췄다', next(o.action for o in outcomes if o.name == '인증 서버 ↔ 결제 서버'))

    def test_a_database_password_already_in_the_url_is_copied_to_the_root(self):
        (self.root / 'trpg-server/.env').write_text(
            'DATABASE_URL=postgresql+asyncpg://game:old-password@db:5432/trpg\n', encoding='utf-8'
        )

        self.fill()

        self.assertEqual(self.env('.env')['GAME_DB_PASSWORD'], 'old-password')

    def test_a_pair_with_two_different_values_is_not_touched(self):
        (self.root / 'auth-server/.env').write_text('BILLING_SECRET=one\n', encoding='utf-8')
        (self.root / 'billing-server/.env').write_text('AUTH_SERVER_SECRET=two\n', encoding='utf-8')

        _, outcomes, _ = self.fill()

        self.assertEqual(self.env('auth-server/.env')['BILLING_SECRET'], 'one')
        self.assertEqual(self.env('billing-server/.env')['AUTH_SERVER_SECRET'], 'two')
        self.assertTrue(any(o.action.startswith('값이 서로 다르다') for o in outcomes))

    def test_a_line_missing_from_an_old_env_is_added_like_the_example(self):
        # .env.example 에 나중에 생긴 줄이다. 그 모양(주석인지)대로 끝에 더한다
        (self.root / '.env').write_text('POSTGRES_PASSWORD=mine', encoding='utf-8')
        (self.root / 'trpg-server/.env').write_text(
            'DATABASE_URL=postgresql+asyncpg://game:pw@db/trpg\n', encoding='utf-8'
        )

        self.fill()

        root = (self.root / '.env').read_text(encoding='utf-8')
        self.assertTrue(root.startswith('POSTGRES_PASSWORD=mine\n'), root)
        self.assertEqual(len(values(root)['MONITOR_DB_PASSWORD']), 64)
        self.assertEqual(len(self.env('trpg-server/.env')['#SIGNAL_SECRET']), 64)

    def test_new_example_lines_are_added_commented_with_their_notes(self):
        # 경보처럼 .env 를 만든 뒤에 생긴 줄이다. 설명과 함께 주석으로 막아 더한다. 동작은 바뀌지 않는다
        (self.root / '.env.example').write_text(
            'POSTGRES_PASSWORD=\n\n# --- 경보 ---\n# 받는 곳의 웹후크\n# ALERT_SLACK_WEBHOOK_URL=\n'
            '# Grafana 의 포트\nGRAFANA_PORT=3000\n',
            encoding='utf-8',
        )
        (self.root / '.env').write_text('POSTGRES_PASSWORD=mine\n', encoding='utf-8')

        _, outcomes, _ = self.fill()

        root = (self.root / '.env').read_text(encoding='utf-8')
        self.assertEqual(
            root,
            'POSTGRES_PASSWORD=mine\n\n# --- 경보 ---\n# 받는 곳의 웹후크\n# ALERT_SLACK_WEBHOOK_URL=\n'
            '# Grafana 의 포트\n# GRAFANA_PORT=3000\n',
        )
        action = next(o.action for o in outcomes if o.name == '.env 의 새 줄')
        self.assertIn('ALERT_SLACK_WEBHOOK_URL, GRAFANA_PORT', action)

    def test_new_lines_follow_windows_line_endings(self):
        (self.root / '.env').write_bytes(b'POSTGRES_PASSWORD=mine\r\n')

        self.fill()

        self.assertNotIn(b'\n', (self.root / '.env').read_bytes().replace(b'\r\n', b''))

    def test_a_secret_line_added_later_is_filled_and_uncommented(self):
        # 알림 서버보다 먼저 만든 게임 서버의 .env 다. 짝의 줄이 없다
        (self.root / 'trpg-server/.env').write_text(
            'DATABASE_URL=postgresql+asyncpg://game:pw@db/trpg\n', encoding='utf-8'
        )

        self.fill()

        game = self.env('trpg-server/.env')
        self.assertEqual(game['NOTIFICATION_SECRET'], self.env('notification-server/.env')['GAME_SERVER_SECRET'])
        self.assertEqual(len(game['#SIGNAL_SECRET']), 64)

    def test_running_again_changes_nothing(self):
        self.fill()
        before = {relative: (self.root / relative).read_text(encoding='utf-8') for relative in ENV_FILES}

        _, outcomes, _ = self.fill()

        after = {relative: (self.root / relative).read_text(encoding='utf-8') for relative in ENV_FILES}
        self.assertEqual(before, after)
        self.assertTrue(all(o.action == '이미 채워져 있다' for o in outcomes))

    def test_windows_line_endings_are_kept(self):
        (self.root / '.env').write_bytes(b'POSTGRES_USER=trpg\r\nPOSTGRES_PASSWORD=\r\n')

        self.fill()

        self.assertIn(b'POSTGRES_PASSWORD=', (self.root / '.env').read_bytes())
        self.assertNotIn(b'\n', (self.root / '.env').read_bytes().replace(b'\r\n', b''))

    def test_dry_run_writes_nothing(self):
        files, _, _ = self.fill(dry_run=True)

        self.assertFalse((self.root / '.env').exists())
        self.assertTrue(files['.env'].created)

    def test_the_report_never_shows_a_value(self):
        output = io.StringIO()
        with mock.patch.object(fill_env, 'REPO_ROOT', self.root), redirect_stdout(output):
            code = main([])

        self.assertEqual(code, 0)
        for relative in ENV_FILES:
            for value in values((self.root / relative).read_text(encoding='utf-8')).values():
                if len(value) == 64:
                    self.assertNotIn(value, output.getvalue())

    def test_the_repository_examples_name_every_listed_secret(self):
        # 표의 이름이 .env.example 에 없으면 그 비밀은 채워지지 않는다(이름을 바꾼 것을 놓친다)
        repository = Path(fill_env.__file__).resolve().parents[1]
        for secret in fill_env.SECRETS:
            for spot in secret.spots:
                example = (repository / spot.file).with_name('.env.example').read_text(encoding='utf-8')
                self.assertRegex(example, rf'(?m)^#?\s*{spot.key}=', f'{spot.file}.example 의 {spot.key}')


if __name__ == '__main__':
    unittest.main()
