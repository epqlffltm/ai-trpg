# auth-server/accounts/tests/test_signing_key_scope.py

"""
서명 키를 받지 않는 프로세스(#274)를 검증한다.

워커와 마이그레이션은 JWT_PRIVATE_KEY_PATH 를 비워 키 없이 뜬다. 그런 프로세스는 토큰을 만들거나 JWKS 를 낼 수 없다.
요청을 받는 서버의 입구(config/wsgi.py)는 키가 없으면 뜨지 않는다.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.jwks import build_jwks
from accounts.key_ring import SigningKeyUnavailableError, current_key_ring, has_signing_key, require_signing_key
from accounts.models import User
from accounts.tokens import issue_token_pair

SERVER_ROOT = Path(settings.BASE_DIR)

# 키를 받지 않은 프로세스의 설정(config/jwt_keys.py 의 NO_KEYS 와 같다)
without_signing_key = override_settings(
    JWT_SIGNING_KEY_PEM=None,
    JWT_PUBLIC_KEY_PEM=None,
    JWT_KEY_ID=None,
    JWT_VERIFICATION_KEYS={},
)


def run_python(code: str, **environment: str) -> subprocess.CompletedProcess:
    """설정을 새로 읽는 파이썬을 서버 폴더에서 띄운다. 지금의 환경 변수에 주어진 값을 덮어쓴다."""
    return subprocess.run(
        [sys.executable, '-c', code],
        # 실패한 끝 코드도 테스트가 직접 본다
        check=False,
        cwd=SERVER_ROOT,
        env={**os.environ, 'DJANGO_SETTINGS_MODULE': 'config.settings', **environment},
        capture_output=True,
        text=True,
        timeout=60,
    )


class KeyRingWithoutASigningKeyTests(SimpleTestCase):
    def test_this_process_has_a_signing_key(self):
        # 테스트를 돌리는 프로세스는 서버와 같은 설정이다
        self.assertTrue(has_signing_key())
        require_signing_key()

    @without_signing_key
    def test_the_key_ring_refuses(self):
        self.assertFalse(has_signing_key())
        with self.assertRaisesMessage(SigningKeyUnavailableError, 'JWT 서명 키가 없습니다'):
            current_key_ring()

    @without_signing_key
    def test_no_jwks_without_a_signing_key(self):
        # 빈 목록을 내면 다른 서버가 모든 토큰을 거부한다. 내지 않는다
        with self.assertRaises(SigningKeyUnavailableError):
            build_jwks()


class IssuingWithoutASigningKeyTests(TestCase):
    @without_signing_key
    def test_no_tokens_without_a_signing_key(self):
        user = User.objects.create_user(username='player_01', email='player@example.com', password='unused-1234')

        with self.assertRaises(SigningKeyUnavailableError):
            issue_token_pair(user)


class ProcessesWithoutAKeyTests(SimpleTestCase):
    def test_the_server_entry_does_not_start_without_a_key(self):
        result = run_python('import config.wsgi', JWT_PRIVATE_KEY_PATH='')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SigningKeyUnavailableError', result.stderr)

    def test_the_server_entry_starts_with_the_key(self):
        result = run_python('import config.wsgi, config.asgi')

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_asgi_entry_does_not_start_without_a_key(self):
        result = run_python('import config.asgi', JWT_PRIVATE_KEY_PATH='')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SigningKeyUnavailableError', result.stderr)

    def test_management_commands_run_without_a_key(self):
        # 워커와 마이그레이션은 manage.py 로 돈다. 설정을 읽고 앱을 모두 불러와도(check) 키를 찾지 않는다
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check'],
            check=False,
            cwd=SERVER_ROOT,
            env={**os.environ, 'JWT_PRIVATE_KEY_PATH': ''},
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
