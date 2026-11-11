# auth-server/config/tests/test_db_limits.py

"""
DB 연결의 시간 한도(config/db_limits.py)와 한도에 걸린 요청의 응답(config/db_timeouts.py)을 실제 DB 로 본다(#1282).

보는 것.
  - 서버의 설정으로 맺은 연결에 한도 셋이 붙는다. 테스트 실행기가 만든 테스트용 DB 의 연결도 그렇다
  - 한도보다 긴 쿼리는 57014 로 끊기고, 다른 연결이 쥔 잠금은 한도까지만 기다리고 55P03 으로 그만둔다
  - 마이그레이션과 주기 명령(docker/cron/auth.crontab)은 한도 없이 붙는다
  - 한도에 걸린 요청은 503 과 Retry-After 다. 다른 DB 오류는 그대로 500 이다
"""

import os
import shlex
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import psycopg
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError, OperationalError, connection
from django.test import SimpleTestCase, TestCase
from django.test.client import Client

import manage
from accounts.views import JwksView
from config import db_limits
from config.db_limits import NO_LIMITS, Limits

CRONTAB = Path(settings.BASE_DIR).parent / 'docker' / 'cron' / 'auth.crontab'
LIMIT_SETTINGS = ('lock_timeout', 'statement_timeout', 'idle_in_transaction_session_timeout')
# 한도 하나만 짧게 둔 연결. 테스트가 오래 기다리지 않고, 다른 한도가 먼저 걸리지 않게 한다
SHORT_QUERY = Limits(lock_timeout_ms=0, statement_timeout_ms=200, idle_in_transaction_timeout_ms=0)
SHORT_LOCK = Limits(lock_timeout_ms=200, statement_timeout_ms=0, idle_in_transaction_timeout_ms=0)
# 잠금을 잡는 쪽이 쓰는 advisory 잠금의 번호. 이 테스트만 쓴다
LOCK_KEY = 1282


def limit_values(cursor) -> dict[str, int]:
    """연결에 걸린 한도 셋(밀리초)."""
    cursor.execute('SELECT name, setting FROM pg_settings WHERE name = ANY(%s)', [list(LIMIT_SETTINGS)])
    return {name: int(value) for name, value in cursor.fetchall()}


@contextmanager
def connection_with(limits: Limits) -> Iterator:
    """테스트용 DB 에 그 한도로 맺은 새 연결(Django 의 연결 하나). 서버의 설정에서 OPTIONS 만 바꾼다."""
    other = connection.copy()
    other.settings_dict['OPTIONS'] = db_limits.with_limits(
        {key: value for key, value in other.settings_dict['OPTIONS'].items() if key != 'options'}, limits
    )
    try:
        with other.cursor() as cursor:
            yield cursor
    finally:
        other.close()


def timed_out(sqlstate: str) -> OperationalError:
    """Django 가 드라이버의 오류를 감싼 모양의 오류. 드라이버의 오류는 __cause__ 에 있다."""
    error = OperationalError('canceling statement')
    error.__cause__ = psycopg.errors.lookup(sqlstate)('canceling statement')
    return error


def crontab_commands() -> set[str]:
    """auth.crontab 의 줄마다 manage.py 다음에 오는 명령의 이름."""
    commands = set()
    for line in CRONTAB.read_text(encoding='utf-8').splitlines():
        words = shlex.split(line, comments=True)
        if 'manage.py' in words:
            commands.add(words[words.index('manage.py') + 1])
    return commands


class ServerConnectionTests(TestCase):
    def test_the_server_connection_has_the_three_limits(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database()')
            (database,) = cursor.fetchone()
            values = limit_values(cursor)

        # 테스트 실행기가 만든 DB 다. 설정의 OPTIONS 가 따라갔다
        self.assertTrue(database.startswith('test_'), database)
        self.assertEqual(
            values,
            {
                'lock_timeout': settings.DATABASE_LIMITS.lock_timeout_ms,
                'statement_timeout': settings.DATABASE_LIMITS.statement_timeout_ms,
                'idle_in_transaction_session_timeout': settings.DATABASE_LIMITS.idle_in_transaction_timeout_ms,
            },
        )
        self.assertTrue(all(value > 0 for value in values.values()), values)

    def test_the_defaults_match_the_fastapi_servers(self):
        self.assertEqual(
            db_limits.limits_from({}),
            Limits(lock_timeout_ms=5_000, statement_timeout_ms=10_000, idle_in_transaction_timeout_ms=60_000),
        )

    def test_a_longer_query_is_canceled(self):
        with connection_with(SHORT_QUERY) as cursor, self.assertRaises(OperationalError) as caught:
            cursor.execute('SELECT pg_sleep(2)')

        self.assertEqual(caught.exception.__cause__.sqlstate, '57014')

    def test_a_held_lock_is_waited_for_only_until_the_limit(self):
        with connection_with(NO_LIMITS) as holder, connection_with(SHORT_LOCK) as waiter:
            holder.execute('SELECT pg_advisory_lock(%s)', [LOCK_KEY])
            started = time.monotonic()
            with self.assertRaises(OperationalError) as caught:
                waiter.execute('SELECT pg_advisory_lock(%s)', [LOCK_KEY])
            waited = time.monotonic() - started
            holder.execute('SELECT pg_advisory_unlock(%s)', [LOCK_KEY])

        self.assertEqual(caught.exception.__cause__.sqlstate, '55P03')
        self.assertLess(waited, 2)


class UnlimitedCommandTests(TestCase):
    def test_migrations_and_the_cron_commands_have_no_limits(self):
        self.assertIn('migrate', db_limits.UNLIMITED_COMMANDS)
        self.assertEqual(crontab_commands() - db_limits.UNLIMITED_COMMANDS, set())
        self.assertTrue(crontab_commands(), '주기 명령을 읽지 못했다')

    def test_the_server_and_the_workers_keep_the_limits(self):
        for command in ('runserver', 'test', 'send_outgoing_mail', 'send_welcome_credits', 'suspend_account'):
            with self.subTest(command=command):
                self.assertFalse(db_limits.is_unlimited_command(['manage.py', command]))
        self.assertFalse(db_limits.is_unlimited_command(['manage.py']))

    def test_an_unlimited_command_reads_zero_limits(self):
        environ = {name: '7000' for name in db_limits.LIMIT_NAMES}

        lifted = db_limits.lift_for_command(['manage.py', 'migrate', '--noinput'], environ)

        self.assertTrue(lifted)
        self.assertEqual(db_limits.limits_from(environ), NO_LIMITS)

    def test_manage_py_lifts_the_limits_before_running_the_command(self):
        def limits_seen(argv):
            seen.append(db_limits.limits_from(os.environ))

        for argv, expected in (
            (['manage.py', 'flushexpiredtokens'], NO_LIMITS),
            (['manage.py', 'send_welcome_credits', '--once'], Limits()),
        ):
            seen = []
            with (
                self.subTest(argv=argv),
                mock.patch.dict(os.environ, {name: '' for name in db_limits.LIMIT_NAMES}),
                mock.patch.object(sys, 'argv', argv),
                mock.patch('django.core.management.execute_from_command_line', side_effect=limits_seen),
            ):
                manage.main()
                self.assertEqual(seen, [expected])

    def test_a_connection_without_limits_has_zero_limits(self):
        with connection_with(NO_LIMITS) as cursor:
            values = limit_values(cursor)

        self.assertEqual(values, dict.fromkeys(LIMIT_SETTINGS, 0))


class LimitSettingTests(SimpleTestCase):
    def test_options_from_the_database_url_are_kept(self):
        options = db_limits.with_limits({'connect_timeout': 5, 'options': '-c search_path=auth'}, Limits())

        self.assertEqual(options['connect_timeout'], 5)
        self.assertEqual(
            options['options'],
            '-c search_path=auth -c lock_timeout=5000 -c statement_timeout=10000 '
            '-c idle_in_transaction_session_timeout=60000',
        )

    def test_a_value_out_of_range_is_refused(self):
        for raw in ('-1', 'abc', '600001'):
            with self.subTest(raw=raw), self.assertRaises(db_limits.InvalidLimitError):
                db_limits.limits_from({db_limits.LOCK_TIMEOUT_NAME: raw})


class TimeoutResponseTests(TestCase):
    def setUp(self):
        self.client = Client(raise_request_exception=False)

    def assert_busy(self, response):
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Retry-After'], '1')
        self.assertEqual(response.json()['code'], 'db_timeout')

    def test_a_timed_out_api_request_is_503(self):
        for sqlstate in ('57014', '55P03'):
            with self.subTest(sqlstate=sqlstate), mock.patch.object(JwksView, 'get', side_effect=timed_out(sqlstate)):
                with self.assertLogs('config.db_timeouts', 'WARNING'):
                    response = self.client.get('/api/v1/auth/jwks')
                self.assert_busy(response)

    def test_a_timed_out_admin_request_is_503(self):
        with mock.patch.object(AdminSite, 'has_permission', side_effect=timed_out('57014')):
            response = self.client.get('/admin/')

        self.assert_busy(response)

    def test_other_database_errors_are_not_hidden(self):
        unreachable = OperationalError('connection refused')
        for error in (unreachable, timed_out('08006'), IntegrityError('duplicate key')):
            with self.subTest(error=repr(error)), mock.patch.object(JwksView, 'get', side_effect=error):
                response = self.client.get('/api/v1/auth/jwks')
                self.assertEqual(response.status_code, 500)
