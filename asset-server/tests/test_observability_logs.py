# asset-server/tests/test_observability_logs.py

"""
로그 한 줄이 공통 규격의 JSON 으로 나가는지, 민감한 값이 가려지는지 검증한다
(app/observability/formatter.py, redaction.py, setup.py). 규격은 docs/observability.md 에 있다.
"""

import json
import logging
import re
import sys

import pytest

from app.core.config import Settings
from app.observability.context import job_scope, request_scope
from app.observability.formatter import JsonFormatter
from app.observability.identifiers import new_trace
from app.observability.redaction import MAX_VALUE_LENGTH, REDACTED, is_sensitive_name, safe_value, scrub_text
from app.observability.setup import JsonLogHandler, attach_json_handler, configure_logging
from tests.conftest import make_test_settings
from tests.logs import TEST_INFO, make_record, render

# 서명까지 갖춘 토큰의 모양. 실제 키로 만든 것이 아니다
JWT = 'eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVlLWhlcmU'


def test_every_line_has_the_common_fields():
    entry = render(make_record('서버가 떴다'))

    assert entry['service'] == 'asset-server'
    assert entry['environment'] == 'test'
    assert entry['version'] == 'test-version'
    assert entry['level'] == 'info'
    assert entry['message'] == '서버가 떴다'
    assert entry['logger'] == 'tests'
    # RFC 3339, UTC, 밀리초까지
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z', entry['timestamp'])


def test_one_line_is_one_json_object():
    line = JsonFormatter(TEST_INFO).format(make_record('첫 줄\n{"level":"error","message":"가짜 줄"}'))

    # 메시지에 줄바꿈을 넣어도 로그는 한 줄이다. 가짜 로그 줄을 끼워 넣을 수 없다
    assert '\n' not in line
    assert json.loads(line)['message'].startswith('첫 줄')


@pytest.mark.parametrize(
    ('level', 'name'),
    [
        (logging.DEBUG, 'debug'),
        (logging.INFO, 'info'),
        (logging.WARNING, 'warning'),
        (logging.ERROR, 'error'),
        (logging.CRITICAL, 'critical'),
        # 사이의 수준은 아래쪽 이름으로 내린다
        (logging.INFO + 5, 'info'),
    ],
)
def test_levels_use_the_names_in_the_spec(level: int, name: str):
    assert render(make_record(level=level))['level'] == name


def test_extra_fields_are_carried():
    entry = render(make_record(operation='persona.create', duration_ms=3821, result='success', retried=False))

    assert entry['operation'] == 'persona.create'
    assert entry['duration_ms'] == 3821
    assert entry['result'] == 'success'
    assert entry['retried'] is False


def test_identifiers_in_scope_are_attached():
    trace = new_trace()

    with request_scope('request-12345', trace):
        in_request = render(make_record())
    with job_scope('job-12345678'):
        in_job = render(make_record())
    outside = render(make_record())

    assert in_request['request_id'] == 'request-12345'
    assert in_request['trace_id'] == trace.trace_id
    assert in_job['job_id'] == 'job-12345678'
    assert 'request_id' not in in_job
    # 걸려 있지 않은 식별자는 빈 글자로 채우지 않고 싣지 않는다
    assert 'request_id' not in outside
    assert 'job_id' not in outside


def test_identifiers_cannot_be_overridden_by_extra_fields():
    with request_scope('request-12345', new_trace()):
        record = make_record()
        # 식별자의 이름으로 다른 값을 적으려는 것
        record.request_id = 'forged-request-id'

    assert render(record)['request_id'] == 'request-12345'


def test_logging_with_an_identifier_name_as_an_extra_field_does_not_raise():
    logger = logging.getLogger('tests.identifier-as-extra')

    # logging 은 이미 있는 칸을 extra 로 덮어쓰려 하면 예외를 낸다. 식별자를 그렇게 붙여 두면 이 줄이 죽는다
    with request_scope('request-12345', new_trace()):
        logger.info('작업을 맡겼다', extra={'job_id': 'job-12345678', 'request_id': 'another'})


def test_the_fixed_fields_cannot_be_overridden():
    record = make_record(service='other-server', environment='production', version='9.9.9')
    # extra={'level': 'debug'} 로 넘긴 것과 같다
    record.level = 'debug'

    entry = render(record)

    assert entry['service'] == 'asset-server'
    assert entry['environment'] == 'test'
    assert entry['version'] == 'test-version'
    assert entry['level'] == 'info'


def test_an_exception_carries_its_kind_and_stack():
    try:
        raise ValueError('값이 틀렸다')
    except ValueError:
        record = make_record('실패했다', logging.ERROR)
        # logging 이 하는 것처럼 지금의 예외를 붙인다
        record.exc_info = sys.exc_info()

    entry = render(record)

    assert entry['error_type'] == 'ValueError'
    assert 'ValueError: 값이 틀렸다' in entry['stack_trace']
    assert 'test_an_exception_carries_its_kind_and_stack' in entry['stack_trace']
    # 오류 코드를 적지 않았으면 기본 코드가 붙는다
    assert entry['error_code'] == 'internal.error'


def test_an_explicit_error_code_wins_over_the_default():
    record = make_record(level=logging.ERROR, error_code='job.failed')
    record.exc_info = (RuntimeError, RuntimeError('죽었다'), None)

    assert render(record)['error_code'] == 'job.failed'


@pytest.mark.parametrize(
    'name',
    [
        'password',
        'new_password',
        'password_hash_value',
        'token',
        'access_token',
        'refreshToken',
        'jwt',
        'authorization',
        'Authorization',
        'cookie',
        'set_cookie',
        'Set-Cookie',
        'secret',
        'client_secret',
        'api_key',
        'apiKey',
        'llm_api_key',
        'private_key',
        'database_url',
        'DATABASE_URL',
        'dsn',
        'email',
        'user_email',
        'code',
        'login_code',
        'verification_code',
        'invite_code',
        'otp',
        'prompt',
        'system_prompt',
        'card_number',
        'payment_key',
        'webhook_signature',
        'cvc',
        'body',
        'content',
        'text',
        'declaration',
        'memo',
        'lore',
        'completion',
        'response',
        'headers',
    ],
)
def test_sensitive_field_names_are_redacted(name: str):
    assert is_sensitive_name(name)
    assert render(make_record(**{name: '드러나면 안 되는 값'}))[name] == REDACTED


@pytest.mark.parametrize(
    'name',
    [
        'operation',
        'status_code',
        'error_code',
        'duration_ms',
        'result',
        'route',
        'method',
        'input_tokens',
        'output_tokens',
        'prompt_version',
        'email_hash',
        'email_masked',
        'table_id',
        'token_type',
        'job_name',
        'model',
        'discarded',
    ],
)
def test_ordinary_field_names_are_kept(name: str):
    assert not is_sensitive_name(name)


def test_a_token_in_the_message_is_redacted():
    entry = render(make_record(f'토큰을 검증하지 못했다: {JWT}'))

    assert JWT not in json.dumps(entry)
    assert '[REDACTED_JWT]' in entry['message']


def test_an_authorization_value_in_any_field_is_redacted():
    entry = render(
        make_record('요청', detail=f'Authorization: Bearer {JWT}', note_for_ops='Basic dXNlcjpwYXNzd29yZA==')
    )

    text = json.dumps(entry)
    assert JWT not in text
    assert 'dXNlcjpwYXNzd29yZA==' not in text


def test_credentials_in_an_address_are_redacted():
    entry = render(make_record('DB 에 닿지 않는다: postgresql+asyncpg://asset:super-secret@db.internal:5432/trpg'))

    assert 'super-secret' not in entry['message']
    assert 'asset:' not in entry['message']
    # 어디에 닿지 못했는지는 남는다
    assert 'db.internal' in entry['message']


def test_an_email_address_is_masked():
    entry = render(make_record('메일을 보내지 못했다: someone.private@example.com'))

    assert 'someone.private' not in entry['message']
    assert 's***@example.com' in entry['message']


def test_a_secret_in_a_stack_trace_is_redacted():
    record = make_record(level=logging.ERROR)
    record.exc_info = (
        RuntimeError,
        RuntimeError(f'connect failed: postgres://asset:super-secret@db/trpg {JWT}'),
        None,
    )

    stack = render(record)['stack_trace']

    assert 'super-secret' not in stack
    assert JWT not in stack


@pytest.mark.parametrize('value', [{'password': 'p'}, ['a', 'b'], ('a',), {1, 2}, object(), b'bytes'])
def test_nested_values_are_not_serialized(value: object):
    entry = render(make_record(payload=value))

    # 묶음과 객체는 풀어 적지 않는다. 종류의 이름만 남는다
    assert entry['payload'] == f'[{type(value).__name__}]'


def test_scalar_values_are_kept_as_they_are():
    assert safe_value('count', 3) == 3
    assert safe_value('ratio', 0.5) == 0.5
    assert safe_value('retried', True) is True
    assert safe_value('reason', None) is None
    # JSON 에 없는 숫자는 글자로 적는다
    assert safe_value('ratio', float('nan')) == 'nan'


def test_a_long_value_is_cut():
    value = scrub_text('가' * (MAX_VALUE_LENGTH + 100))

    assert len(value) == MAX_VALUE_LENGTH + 1
    assert value.endswith('…')


def test_the_json_handler_is_attached_once():
    root = logging.Logger('root-for-test')
    other = logging.NullHandler()
    root.addHandler(other)

    attach_json_handler(root, TEST_INFO)
    attach_json_handler(root, TEST_INFO)

    # 다른 처리기는 건드리지 않는다. 테스트 도구가 달아 둔 것이 떨어지지 않는다
    assert other in root.handlers
    assert sum(isinstance(handler, JsonLogHandler) for handler in root.handlers) == 1


def test_configuring_routes_uvicorn_logs_and_silences_its_access_log():
    configure_logging(make_test_settings())

    assert logging.getLogger('uvicorn.error').propagate is True
    assert logging.getLogger('uvicorn.error').handlers == []
    assert logging.getLogger('uvicorn.access').disabled is True


def test_the_settings_carry_who_this_server_is():
    settings = make_test_settings(app_environment='production', app_version='3f2a1b9', log_level='warning')

    assert settings.app_environment == 'production'
    assert settings.app_version == '3f2a1b9'
    assert settings.log_level == 'warning'


def test_the_defaults_are_safe_for_local_development(monkeypatch: pytest.MonkeyPatch):
    # 설정을 읽는 그대로 본다. 개발자의 환경 변수와 .env 에 적힌 값은 빼고 본다
    for name in ('APP_ENVIRONMENT', 'APP_VERSION', 'LOG_LEVEL'):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(
        _env_file=None,
        database_url='postgresql+asyncpg://asset:pw@127.0.0.1:5432/trpg',
        auth_jwks_url='http://auth.test/api/v1/auth/jwks',
    )

    assert settings.app_environment == 'development'
    assert settings.app_version == 'dev'
    assert settings.log_level == 'info'


@pytest.mark.parametrize(
    'overrides',
    [{'app_environment': 'Prod\nuction'}, {'app_version': 'v1\n{"level":"error"}'}, {'log_level': 'verbose'}],
)
def test_malformed_values_are_rejected_at_startup(overrides: dict):
    # 이 값들은 로그의 모든 줄에 실린다. 줄바꿈이 든 값을 받지 않는다
    with pytest.raises(ValueError, match='validation error'):
        make_test_settings(**overrides)
