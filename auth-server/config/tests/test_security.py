# auth-server/config/tests/test_security.py

"""
운영 환경과 staging 의 보안 설정(config/security.py, config/environments.py)을 확인한다.

함수는 직접 부른다. 설정 파일에 제대로 이어졌는지는 설정을 새로 읽는 manage.py 를 따로 띄워 본다.
지금 테스트가 도는 프로세스의 설정은 이미 읽혀 있어서, 환경 변수를 바꿔도 다시 읽히지 않는다.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.environments import is_deployed, is_production
from config.security import (
    DEVELOPMENT_COOKIE_ORIGINS,
    FORWARDED_PROTO_HEADER,
    default_cookie_origins,
    parse_cookie_origin,
    proxy_ssl_header,
    require_cookie_origins,
    require_own_audience,
    require_secure_refresh_cookie,
    secure_cookies,
)

# manage.py 가 있는 폴더(auth-server)
SERVER_ROOT = Path(__file__).resolve().parents[2]

# 운영 환경으로 설정을 읽을 때 꼭 있어야 하는 값. 이 테스트에서만 쓴다
PRODUCTION_ENVIRONMENT = {
    'APP_ENVIRONMENT': 'production',
    'DEBUG': 'false',
    # check --deploy 는 50자가 안 되거나 글자 종류가 적은 비밀키를 경고한다
    'SECRET_KEY': 'test-only-production-secret-key-0123456789-abcdefghijklmnopqrstuvwxyz',
    # 운영에서는 메일 서버가 있어야 뜬다(config/mail_backends.py). 메일 서버를 적으면 계정도 적어야 한다
    'SMTP_HOST': 'smtp.example.com',
    'SMTP_USER': 'test-only@example.com',
    'SMTP_PASSWORD': 'test-only-password',
    'REFRESH_COOKIE_SECURE': 'true',
    # 비어 있으면 check --deploy 가 경고한다(W020). 운영에서는 실제 도메인을 적는다
    'ALLOWED_HOSTS': 'api.example.com',
    # 운영에는 기본값이 없다. 화면을 여는 주소를 적는다
    'REFRESH_COOKIE_ALLOWED_ORIGINS': 'https://play.example.com',
}

# staging 으로 설정을 읽을 때 꼭 있어야 하는 값. 메일 서버와 본인인증 업체는 적지 않는다(터미널 메일, 가짜 업체로 뜬다)
STAGING_ENVIRONMENT = {
    'APP_ENVIRONMENT': 'staging',
    'DEBUG': 'false',
    'SECRET_KEY': 'test-only-staging-secret-key-0123456789-abcdefghijklmnopqrstuvwxyz',
    'SMTP_HOST': '',
    'REFRESH_COOKIE_SECURE': 'true',
    'ALLOWED_HOSTS': 'staging.example.com',
    'REFRESH_COOKIE_ALLOWED_ORIGINS': 'https://staging.example.com',
}


def run_manage(*arguments: str, **environment: str) -> subprocess.CompletedProcess:
    """설정을 새로 읽는 manage.py 를 띄운다. 지금의 환경 변수에 주어진 값을 덮어쓴다."""
    return subprocess.run(
        [sys.executable, 'manage.py', *arguments],
        # 실패한 끝 코드도 테스트가 직접 본다
        check=False,
        cwd=SERVER_ROOT,
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        timeout=60,
    )


class FunctionTests(SimpleTestCase):
    def test_only_production_is_production(self):
        self.assertTrue(is_production('production'))
        self.assertFalse(is_production('development'))
        self.assertFalse(is_production('staging'))

    def test_staging_and_production_are_deployed(self):
        self.assertTrue(is_deployed('production'))
        self.assertTrue(is_deployed('staging'))
        self.assertFalse(is_deployed('development'))
        self.assertFalse(is_deployed('test'))

    def test_session_and_csrf_cookies_are_secure_only_in_production(self):
        # 관리자 화면의 쿠키다. staging 은 SSH 터널(localhost)로만 열어 바꾸지 않았다
        self.assertTrue(secure_cookies('production'))
        self.assertFalse(secure_cookies('staging'))
        self.assertFalse(secure_cookies('development'))

    def test_deployed_environments_refuse_an_insecure_refresh_cookie(self):
        for environment in ('staging', 'production'):
            with self.subTest(environment=environment), self.assertRaises(ImproperlyConfigured):
                require_secure_refresh_cookie(False, environment)

    def test_development_may_turn_the_refresh_cookie_secure_off(self):
        require_secure_refresh_cookie(False, 'development')
        require_secure_refresh_cookie(True, 'staging')
        require_secure_refresh_cookie(True, 'production')

    def test_the_token_audiences_must_name_this_server(self):
        # 다시 동의할 사람의 토큰은 이 이름만 싣는다(#450). 목록에 없으면 그 사람은 동의를 마칠 길이 없다
        require_own_audience('ai-trpg-auth', ['ai-trpg-auth', 'ai-trpg-game'])
        with self.assertRaises(ImproperlyConfigured):
            require_own_audience('ai-trpg-auth', ['ai-trpg-game', 'ai-trpg-billing'])

    def test_the_forwarded_proto_is_trusted_only_behind_a_proxy(self):
        self.assertIsNone(proxy_ssl_header(0))
        self.assertEqual(proxy_ssl_header(1), FORWARDED_PROTO_HEADER)


class CookieOriginFunctionTests(SimpleTestCase):
    def test_development_defaults_to_the_compose_proxy(self):
        self.assertEqual(default_cookie_origins('development'), list(DEVELOPMENT_COOKIE_ORIGINS))

    def test_deployed_environments_have_no_default(self):
        # 개발의 기본값(http://localhost:8080)이 staging 에 들어가면 화면의 도메인과 맞지 않는다
        self.assertEqual(default_cookie_origins('production'), [])
        self.assertEqual(default_cookie_origins('staging'), [])

    def test_origin_is_written_the_way_browsers_send_it(self):
        self.assertEqual(parse_cookie_origin(' HTTPS://Play.Example.com/ '), 'https://play.example.com')
        self.assertEqual(parse_cookie_origin('http://localhost:8080'), 'http://localhost:8080')
        self.assertEqual(parse_cookie_origin('http://[::1]:8080'), 'http://[::1]:8080')

    def test_origin_with_a_path_or_without_a_scheme_is_refused(self):
        for value in ('https://play.example.com/app', 'play.example.com', 'https://play.example.com?x=1', '*', ''):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                parse_cookie_origin(value)

    def test_empty_list_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            require_cookie_origins([], 'development')

    def test_deployed_environments_allow_only_https(self):
        require_cookie_origins(['http://localhost:8080'], 'development')
        for environment in ('staging', 'production'):
            with self.subTest(environment=environment):
                require_cookie_origins(['https://play.example.com'], environment)
                with self.assertRaises(ImproperlyConfigured):
                    require_cookie_origins(['https://play.example.com', 'http://play.example.com'], environment)


class ProductionSettingsTests(SimpleTestCase):
    def test_production_passes_the_deploy_check_without_warnings(self):
        result = run_manage('check', '--deploy', '--fail-level', 'WARNING', **PRODUCTION_ENVIRONMENT)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_refuses_to_start_with_an_insecure_refresh_cookie(self):
        result = run_manage('check', **{**PRODUCTION_ENVIRONMENT, 'REFRESH_COOKIE_SECURE': 'false'})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REFRESH_COOKIE_SECURE', result.stderr)

    def test_production_refuses_to_start_without_cookie_origins(self):
        environment = {
            key: value for key, value in PRODUCTION_ENVIRONMENT.items() if key != 'REFRESH_COOKIE_ALLOWED_ORIGINS'
        }
        result = run_manage('check', **environment)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REFRESH_COOKIE_ALLOWED_ORIGINS', result.stderr)

    def test_production_refuses_to_start_with_an_http_cookie_origin(self):
        result = run_manage(
            'check', **{**PRODUCTION_ENVIRONMENT, 'REFRESH_COOKIE_ALLOWED_ORIGINS': 'http://play.example.com'}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('https', result.stderr)

    def test_production_cookies_are_secure(self):
        result = run_manage(
            'shell',
            '-c',
            'from django.conf import settings; print(settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE)',
            **PRODUCTION_ENVIRONMENT,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[-2:], ['True', 'True'])

    def test_staging_starts_with_terminal_mail_and_the_fake_identity_provider(self):
        # 운영자 혼자 쓰는 서버다. 메일 서버와 실제 본인인증 업체 없이 뜬다.
        # 남이 들어오는 것은 nginx 의 허용 주소가 막는다
        code = 'from django.conf import settings; print(settings.IDENTITY_PROVIDER, settings.SESSION_COOKIE_SECURE)'
        result = run_manage('shell', '-c', code, **STAGING_ENVIRONMENT)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[-2:], ['fake', 'False'])

    def test_staging_refuses_to_start_with_debug(self):
        result = run_manage('check', **{**STAGING_ENVIRONMENT, 'DEBUG': 'true'})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DEBUG', result.stderr)

    def test_staging_refuses_to_start_with_an_insecure_refresh_cookie(self):
        result = run_manage('check', **{**STAGING_ENVIRONMENT, 'REFRESH_COOKIE_SECURE': 'false'})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REFRESH_COOKIE_SECURE', result.stderr)

    def test_staging_refuses_to_start_without_cookie_origins(self):
        environment = {
            key: value for key, value in STAGING_ENVIRONMENT.items() if key != 'REFRESH_COOKIE_ALLOWED_ORIGINS'
        }
        result = run_manage('check', **environment)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REFRESH_COOKIE_ALLOWED_ORIGINS', result.stderr)

    def test_staging_refuses_to_start_with_an_http_cookie_origin(self):
        result = run_manage(
            'check', **{**STAGING_ENVIRONMENT, 'REFRESH_COOKIE_ALLOWED_ORIGINS': 'http://staging.example.com'}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('https', result.stderr)

    def test_the_proxy_header_follows_the_proxy_count(self):
        code = 'from django.conf import settings; print(settings.SECURE_PROXY_SSL_HEADER)'
        behind = run_manage('shell', '-c', code, TRUSTED_PROXY_COUNT='1')
        direct = run_manage('shell', '-c', code, TRUSTED_PROXY_COUNT='0')

        self.assertIn('HTTP_X_FORWARDED_PROTO', behind.stdout)
        self.assertIn('None', direct.stdout)
