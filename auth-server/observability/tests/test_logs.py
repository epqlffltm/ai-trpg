# auth-server/observability/tests/test_logs.py

"""
로그 한 줄이 공통 규격의 JSON 으로 나가는지, 민감한 값이 가려지는지 검증한다
(observability/formatter.py, redaction.py, setup.py). 규격은 docs/observability.md 에 있다.
"""

import json
import logging
import sys

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.mail_backends import forbid_debug_when_deployed, require_real_mailer_in_production
from observability.context import job_scope, request_scope
from observability.formatter import JsonFormatter
from observability.identifiers import new_trace
from observability.redaction import MAX_VALUE_LENGTH, REDACTED, is_sensitive_name, safe_value, scrub_text
from observability.setup import LOGGED_UNHANDLED_ATTRIBUTE, OnlyUnloggedServerErrors
from observability.tests.helpers import TEST_INFO, make_record, render

# 서명까지 갖춘 토큰의 모양. 실제 키로 만든 것이 아니다
JWT = 'eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVlLWhlcmU'

SENSITIVE_NAMES = [
    'password', 'new_password', 'password_hash_value', 'token', 'access_token', 'refreshToken', 'jwt',
    'authorization', 'Authorization', 'cookie', 'set_cookie', 'Set-Cookie', 'secret', 'client_secret',
    'api_key', 'apiKey', 'private_key', 'database_url', 'DATABASE_URL', 'dsn', 'email', 'user_email', 'to_email',
    'code', 'login_code', 'verification_code', 'reset_token', 'otp', 'prompt', 'card_number', 'cvc',
    'payment_key', 'signature',
    'body', 'content', 'text', 'headers',
]  # fmt: skip
ORDINARY_NAMES = [
    'operation', 'status_code', 'error_code', 'duration_ms', 'result', 'route', 'method',
    'email_hash', 'email_masked', 'user_id', 'token_type', 'attempts', 'mail_id',
]  # fmt: skip


class CommonFieldsTests(SimpleTestCase):
    def test_every_line_has_the_common_fields(self):
        entry = render(make_record('서버가 떴다'))

        self.assertEqual(entry['service'], 'auth-server')
        self.assertEqual(entry['environment'], 'test')
        self.assertEqual(entry['version'], 'test-version')
        self.assertEqual(entry['level'], 'info')
        self.assertEqual(entry['message'], '서버가 떴다')
        self.assertEqual(entry['logger'], 'tests')
        # RFC 3339, UTC, 밀리초까지
        self.assertRegex(entry['timestamp'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')

    def test_one_line_is_one_json_object(self):
        line = JsonFormatter(TEST_INFO).format(make_record('첫 줄\n{"level":"error","message":"가짜 줄"}'))

        # 메시지에 줄바꿈을 넣어도 로그는 한 줄이다. 가짜 로그 줄을 끼워 넣을 수 없다
        self.assertNotIn('\n', line)
        self.assertTrue(json.loads(line)['message'].startswith('첫 줄'))

    def test_levels_use_the_names_in_the_spec(self):
        levels = {
            logging.DEBUG: 'debug',
            logging.INFO: 'info',
            logging.WARNING: 'warning',
            logging.ERROR: 'error',
            logging.CRITICAL: 'critical',
        }
        for level, name in levels.items():
            with self.subTest(level=name):
                self.assertEqual(render(make_record(level=level))['level'], name)

    def test_extra_fields_are_carried(self):
        entry = render(make_record(operation='mail.deliver_outgoing', duration_ms=12, result='success'))

        self.assertEqual(entry['operation'], 'mail.deliver_outgoing')
        self.assertEqual(entry['duration_ms'], 12)
        self.assertEqual(entry['result'], 'success')

    def test_identifiers_in_scope_are_attached(self):
        trace = new_trace()

        with request_scope('request-12345', trace):
            in_request = render(make_record())
        with job_scope('job-12345678'):
            in_job = render(make_record())
        outside = render(make_record())

        self.assertEqual(in_request['request_id'], 'request-12345')
        self.assertEqual(in_request['trace_id'], trace.trace_id)
        self.assertEqual(in_job['job_id'], 'job-12345678')
        self.assertNotIn('request_id', in_job)
        # 걸려 있지 않은 식별자는 빈 글자로 채우지 않고 싣지 않는다
        self.assertNotIn('request_id', outside)
        self.assertNotIn('job_id', outside)

    def test_identifiers_cannot_be_overridden_by_extra_fields(self):
        with request_scope('request-12345', new_trace()):
            record = make_record()
            record.request_id = 'forged-request-id'

        self.assertEqual(render(record)['request_id'], 'request-12345')

    def test_logging_with_an_identifier_name_as_an_extra_field_does_not_raise(self):
        logger = logging.getLogger('tests.identifier-as-extra')

        # logging 은 이미 있는 칸을 extra 로 덮어쓰려 하면 예외를 낸다. 식별자를 그렇게 붙여 두면 이 줄이 죽는다
        with request_scope('request-12345', new_trace()), self.assertLogs(logger, logging.INFO):
            logger.info('작업을 맡겼다', extra={'job_id': 'job-12345678', 'request_id': 'another'})

    def test_the_fixed_fields_cannot_be_overridden(self):
        record = make_record(service='other-server', environment='production', version='9.9.9')
        record.level = 'debug'

        entry = render(record)

        self.assertEqual(entry['service'], 'auth-server')
        self.assertEqual(entry['environment'], 'test')
        self.assertEqual(entry['version'], 'test-version')
        self.assertEqual(entry['level'], 'info')

    def test_an_exception_carries_its_kind_and_stack(self):
        try:
            raise ValueError('값이 틀렸다')
        except ValueError:
            record = make_record('실패했다', logging.ERROR)
            record.exc_info = sys.exc_info()

        entry = render(record)

        self.assertEqual(entry['error_type'], 'ValueError')
        self.assertIn('ValueError: 값이 틀렸다', entry['stack_trace'])
        # 오류 코드를 적지 않았으면 기본 코드가 붙는다
        self.assertEqual(entry['error_code'], 'internal.error')

    def test_an_explicit_error_code_wins_over_the_default(self):
        record = make_record(level=logging.ERROR, error_code='job.failed')
        record.exc_info = (RuntimeError, RuntimeError('죽었다'), None)

        self.assertEqual(render(record)['error_code'], 'job.failed')

    def test_the_request_object_django_attaches_is_not_serialized(self):
        # Django 는 요청에 관한 로그에 요청 객체를 딸려 보낸다. 머리말과 본문이 통째로 든 것이다
        entry = render(make_record(request=object(), status_code=500))

        self.assertNotIn('request', entry)
        self.assertEqual(entry['status_code'], 500)


class RedactionTests(SimpleTestCase):
    def test_sensitive_field_names_are_redacted(self):
        for name in SENSITIVE_NAMES:
            with self.subTest(name=name):
                self.assertTrue(is_sensitive_name(name))
                self.assertEqual(render(make_record(**{name: '드러나면 안 되는 값'}))[name], REDACTED)

    def test_ordinary_field_names_are_kept(self):
        for name in ORDINARY_NAMES:
            with self.subTest(name=name):
                self.assertFalse(is_sensitive_name(name))

    def test_a_token_in_the_message_is_redacted(self):
        entry = render(make_record(f'토큰을 검증하지 못했다: {JWT}'))

        self.assertNotIn(JWT, json.dumps(entry))
        self.assertIn('[REDACTED_JWT]', entry['message'])

    def test_an_authorization_value_in_any_field_is_redacted(self):
        entry = render(make_record('요청', detail=f'Authorization: Bearer {JWT}', hint='Basic dXNlcjpwYXNzd29yZA=='))

        text = json.dumps(entry)
        self.assertNotIn(JWT, text)
        self.assertNotIn('dXNlcjpwYXNzd29yZA==', text)

    def test_credentials_in_an_address_are_redacted(self):
        entry = render(make_record('DB 에 닿지 않는다: postgres://auth:super-secret@db.internal:5432/trpg'))

        self.assertNotIn('super-secret', entry['message'])
        self.assertNotIn('auth:', entry['message'])
        # 어디에 닿지 못했는지는 남는다
        self.assertIn('db.internal', entry['message'])

    def test_an_email_address_is_masked(self):
        # 메일 서버가 받는 사람을 거부하면 그 오류의 글에 주소가 들어 있다(accounts/outbox.py)
        entry = render(make_record("마지막 오류=SMTPRecipientsRefused: {'someone.private@example.com': (550, b'no')}"))

        self.assertNotIn('someone.private', entry['message'])
        self.assertIn('s***@example.com', entry['message'])

    def test_a_secret_in_a_stack_trace_is_redacted(self):
        record = make_record(level=logging.ERROR)
        record.exc_info = (RuntimeError, RuntimeError(f'failed: postgres://auth:super-secret@db/trpg {JWT}'), None)

        stack = render(record)['stack_trace']

        self.assertNotIn('super-secret', stack)
        self.assertNotIn(JWT, stack)

    def test_nested_values_are_not_serialized(self):
        for value in [{'password': 'p'}, ['a', 'b'], ('a',), object(), b'bytes']:
            with self.subTest(kind=type(value).__name__):
                entry = render(make_record(payload=value))

                # 묶음과 객체는 풀어 적지 않는다. 종류의 이름만 남는다
                self.assertEqual(entry['payload'], f'[{type(value).__name__}]')

    def test_scalar_values_are_kept_as_they_are(self):
        self.assertEqual(safe_value('count', 3), 3)
        self.assertEqual(safe_value('ratio', 0.5), 0.5)
        self.assertIs(safe_value('retried', True), True)
        self.assertIsNone(safe_value('reason', None))
        # JSON 에 없는 숫자는 글자로 적는다
        self.assertEqual(safe_value('ratio', float('nan')), 'nan')

    def test_a_long_value_is_cut(self):
        value = scrub_text('가' * (MAX_VALUE_LENGTH + 100))

        self.assertEqual(len(value), MAX_VALUE_LENGTH + 1)
        self.assertTrue(value.endswith('…'))


class DjangoRequestFilterTests(SimpleTestCase):
    """Django 가 요청에 관해 적는 줄을 거르는 것(OnlyUnloggedServerErrors)."""

    def keeps(self, exception: BaseException | None = None, **fields: object) -> bool:
        record = make_record(level=logging.ERROR, **fields)
        if exception is not None:
            record.exc_info = (type(exception), exception, exception.__traceback__)
        return OnlyUnloggedServerErrors().filter(record)

    def test_client_error_lines_are_dropped(self):
        # "Not Found: /주소" 같은 줄이다. 요청이 끝난 줄은 미들웨어가 이미 적는다
        self.assertFalse(self.keeps(status_code=404))
        self.assertFalse(self.keeps(status_code=400))

    def test_an_exception_the_middleware_already_logged_is_dropped(self):
        request = type('Request', (), {LOGGED_UNHANDLED_ATTRIBUTE: True})()

        self.assertFalse(self.keeps(RuntimeError('boom'), status_code=500, request=request))

    def test_a_server_error_answer_without_an_exception_is_dropped(self):
        # 뷰가 스스로 돌려준 503(readiness) 같은 것이다. 요청이 끝난 줄은 미들웨어가 제 수준으로 적는다
        request = type('Request', (), {})()

        self.assertFalse(self.keeps(status_code=503, request=request))
        self.assertFalse(self.keeps(status_code=500, request=request))

    def test_an_exception_nobody_else_logged_is_kept(self):
        request = type('Request', (), {})()

        self.assertTrue(self.keeps(RuntimeError('boom'), status_code=500, request=request))
        self.assertTrue(self.keeps(RuntimeError('boom')))


class SettingsTests(SimpleTestCase):
    def test_logging_goes_through_the_json_formatter(self):
        handlers = logging.getLogger().handlers

        self.assertTrue(any(isinstance(handler.formatter, JsonFormatter) for handler in handlers))

    def test_the_settings_carry_who_this_server_is(self):
        info = settings.LOGGING['formatters']['json']['info']

        self.assertEqual(info.service, 'auth-server')
        self.assertEqual(info.environment, settings.APP_ENVIRONMENT)
        self.assertEqual(info.version, settings.APP_VERSION)

    def test_the_request_middleware_comes_first(self):
        self.assertEqual(settings.MIDDLEWARE[0], 'observability.middleware.RequestLoggingMiddleware')

    def test_the_development_server_request_line_is_silenced(self):
        # 그 줄에는 실제 주소가 주소 뒤에 붙은 값까지 그대로 적힌다
        server_logger = logging.getLogger('django.server')

        self.assertFalse(server_logger.propagate)
        # 처리기가 하나도 없으면 logging 이 경고 이상을 형식 없이 그대로 찍는다. 아무것도 적지 않는 것을 달아 둔다
        self.assertEqual([type(handler) for handler in server_logger.handlers], [logging.NullHandler])


class ConsoleMailInProductionTests(SimpleTestCase):
    """터미널에 메일을 출력하는 개발용 방식을 운영에서 막는 것(config/mail_backends.py)."""

    def test_production_without_a_mail_server_refuses_to_start(self):
        # 터미널 출력에는 받는 사람의 주소와 인증 코드가 그대로 찍힌다. 운영에서는 그것이 로그에 남는다
        with self.assertRaisesMessage(ImproperlyConfigured, 'SMTP_HOST'):
            require_real_mailer_in_production('', 'production')

    def test_production_with_a_mail_server_starts(self):
        require_real_mailer_in_production('smtp.example.com', 'production')

    def test_deployed_environments_with_debug_refuse_to_start(self):
        # DEBUG 가 켜져 있으면 예외의 응답에 호출 기록과 설정값이 실린다. staging 도 도메인 뒤에 있다
        for environment in ('staging', 'production'):
            with self.subTest(environment=environment), self.assertRaisesMessage(ImproperlyConfigured, 'DEBUG'):
                forbid_debug_when_deployed(True, environment)

    def test_debug_is_allowed_only_on_this_pc(self):
        for environment in ('staging', 'production'):
            with self.subTest(environment=environment):
                forbid_debug_when_deployed(False, environment)
        for environment in ('development', 'test'):
            with self.subTest(environment=environment):
                forbid_debug_when_deployed(True, environment)

    def test_other_environments_may_print_mail_to_the_terminal(self):
        for environment in ('development', 'test', 'staging'):
            with self.subTest(environment=environment):
                require_real_mailer_in_production('', environment)
