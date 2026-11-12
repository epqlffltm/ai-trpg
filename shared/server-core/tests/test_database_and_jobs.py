# shared/server-core/tests/test_database_and_jobs.py

"""
DB 에 닿지 않고 볼 수 있는 것을 검증한다.
실제 쿼리의 span, 연결을 기다린 시간, DB 의 응답은 서버의 테스트가 실제 DB 로 본다.

  - DB 연결(server_core/database.py): search_path, 풀, 세션의 틀, 요청마다의 세션
  - 쿼리의 span(observability/db_spans.py): 문장의 종류와 테이블, SQLSTATE, span 을 시작하고 끝내는 자리
  - 작업의 메트릭(observability/metrics.py 의 measured_job), DB 의 상태와 연결 풀의 값
  - 그 밖의 작은 것: 지금의 추적, 작업 식별자, 처리기가 달려 있는가, 받은 traceparent 를 부모로
"""

import asyncio
import logging
from types import SimpleNamespace
from typing import cast

import pytest
import sqlalchemy
from fastapi import HTTPException, Request
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic import ValidationError
from sqlalchemy.engine import Connection, ExceptionContext, ExecutionContext
from sqlalchemy.exc import DBAPIError

from server_core.database import (
    LOCK_NOT_AVAILABLE,
    NO_LIMITS,
    QUERY_CANCELED,
    Limits,
    affected_rows,
    create_engine,
    create_session_factory,
    get_session,
    limit_settings,
    limits_of,
    search_path,
)
from server_core.observability import metrics as metrics_module
from server_core.observability.context import current_trace, request_scope
from server_core.observability.db_spans import (
    SPAN_ATTRIBUTE,
    end_query_span,
    fail_query_span,
    instrument_engine,
    operation_of,
    query_span_name,
    sql_state,
    start_query_span,
    table_of,
)
from server_core.observability.identifiers import new_job_id, new_trace
from server_core.observability.idle_rounds import DropIdleRounds
from server_core.observability.metrics import (
    PoolStats,
    measured_job,
    record_db_up,
    record_pool_wait,
    watch_pool,
)
from server_core.observability.pool_metrics import MeteredPool, pool_stats
from server_core.observability.setup import JsonLogHandler, has_json_handler
from server_core.observability.spans import JOB_FAILED_ERROR_CODE, job_span, remote_parent, tag_current_span
from server_core.testing.metrics import MetricsRecorder
from server_core.testing.spans import SpanRecorder
from tests.conftest import make_test_settings

# --- DB 연결 ---


def test_the_search_path_puts_the_schema_first():
    assert search_path('game') == 'game'
    assert search_path('game_test', ['extensions']) == 'game_test, extensions'


async def test_the_engine_is_made_without_connecting():
    settings = make_test_settings(db_pool_size=2, db_max_overflow=1)
    engine = create_engine(settings)

    pool = engine.sync_engine.pool
    assert isinstance(pool, MeteredPool)
    assert (pool.size(), pool._max_overflow) == (2, 1)
    stats = pool_stats(engine, settings.db_max_connections)
    assert (stats.idle(), stats.in_use(), stats.maximum) == (0, 0, 3)
    await engine.dispose()


def test_the_default_pool_is_sqlalchemys():
    settings = make_test_settings()

    assert (settings.db_pool_size, settings.db_max_overflow, settings.db_max_connections) == (5, 10, 15)


def test_the_pool_size_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv('DB_POOL_SIZE', '2')
    monkeypatch.setenv('DB_MAX_OVERFLOW', '3')

    assert make_test_settings().db_max_connections == 5


@pytest.mark.parametrize(('field', 'value'), [('db_pool_size', 0), ('db_pool_size', 51), ('db_max_overflow', -1)])
def test_a_pool_size_out_of_range_is_refused(field, value):
    with pytest.raises(ValidationError):
        make_test_settings(**{field: value})


def test_affected_rows_counts_what_a_statement_changed():
    # 커서의 결과만 본다. 메모리의 SQLite 로 충분하다
    engine = sqlalchemy.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sqlalchemy.text('CREATE TABLE t (n INTEGER)'))
        connection.execute(sqlalchemy.text('INSERT INTO t VALUES (1), (2), (3)'))

        deleted = affected_rows(connection.execute(sqlalchemy.text('DELETE FROM t WHERE n > 1')))
        none = affected_rows(connection.execute(sqlalchemy.text('UPDATE t SET n = 9 WHERE n > 5')))
    engine.dispose()

    assert (deleted, none) == (2, 0)


async def test_a_request_gets_a_session_from_the_app():
    engine = create_engine(make_test_settings())
    factory = create_session_factory(engine, info={'signer': 'test'})
    request = cast(Request, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_factory=factory))))

    sessions = get_session(request)
    session = await anext(sessions)
    assert session.info == {'signer': 'test'}
    await sessions.aclose()
    await engine.dispose()


# --- 시간 한도(#1260) ---


class DriverError(Exception):
    """드라이버의 오류. 코드(sqlstate)만 흉내 낸다."""

    def __init__(self, message: str, sqlstate: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


def timed_out(code: str) -> DBAPIError:
    """DB 가 그 코드로 끊은 오류."""
    return DBAPIError('select 1', {}, DriverError('끊었다', code))


async def use_session(request: Request, error: Exception) -> None:
    """요청의 세션을 받은 뒤 그 요청이 error 로 끝나게 한다."""
    sessions = get_session(request)
    await anext(sessions)
    await sessions.athrow(error)


def request_with(engine) -> Request:
    """그 엔진의 세션을 쓰는 요청. 앱의 세션 공장만 가진다."""
    factory = create_session_factory(engine)
    return cast(Request, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_factory=factory))))


def test_the_server_limits_come_from_the_settings():
    settings = make_test_settings(
        db_lock_timeout_ms=1_500, db_statement_timeout_ms=2_500, db_idle_in_transaction_timeout_ms=3_500
    )

    assert limits_of(settings) == Limits(1_500, 2_500, 3_500)


def test_the_server_has_limits_unless_they_are_turned_off():
    """아무것도 적지 않아도 서버의 연결에는 한도가 있다. 없으면 멈춘 트랜잭션 하나가 풀을 다 잡는다."""
    limits = limits_of(make_test_settings())

    assert limits.lock_timeout_ms > 0
    assert limits.statement_timeout_ms > 0
    assert limits.idle_in_transaction_timeout_ms > 0


def test_the_limits_go_to_the_database_in_milliseconds():
    assert limit_settings(Limits(5_000, 10_000, 60_000)) == {
        'lock_timeout': '5000',
        'statement_timeout': '10000',
        'idle_in_transaction_session_timeout': '60000',
    }


def test_no_limits_turns_every_limit_off():
    """마이그레이션과 스크립트의 것. 0 을 넘겨 DB 계정에 걸린 한도가 있어도 끈다."""
    assert set(limit_settings(NO_LIMITS).values()) == {'0'}


@pytest.mark.parametrize(
    'field', ['db_lock_timeout_ms', 'db_statement_timeout_ms', 'db_idle_in_transaction_timeout_ms']
)
def test_a_negative_limit_is_refused(field: str):
    with pytest.raises(ValidationError):
        make_test_settings(**{field: -1})


@pytest.mark.parametrize('code', [LOCK_NOT_AVAILABLE, QUERY_CANCELED])
async def test_a_request_cut_by_a_limit_is_503_with_retry_after(code: str):
    engine = create_engine(make_test_settings())

    with pytest.raises(HTTPException) as raised:
        await use_session(request_with(engine), timed_out(code))

    assert raised.value.status_code == 503
    assert raised.value.headers == {'Retry-After': '1'}
    await engine.dispose()


async def test_another_database_error_is_not_turned_into_503():
    """한도가 아닌 오류(유일 제약 등)는 그대로 올라간다. 503 으로 가리면 고칠 버그가 숨는다."""
    engine = create_engine(make_test_settings())
    error = timed_out('23505')

    with pytest.raises(DBAPIError) as raised:
        await use_session(request_with(engine), error)

    assert raised.value is error
    await engine.dispose()


# --- 쿼리의 span ---


@pytest.mark.parametrize(
    ('statement', 'operation'),
    [
        ('select 1', 'SELECT'),
        ('  DELETE FROM x', 'DELETE'),
        ('', 'QUERY'),
        ('(SELECT 1)', 'QUERY'),
        ('A' * 17, 'QUERY'),
    ],
)
def test_the_operation_is_the_first_word(statement: str, operation: str):
    assert operation_of(statement) == operation


def test_a_statement_without_one_table_has_no_table():
    assert table_of(None) is None
    assert query_span_name('SELECT', None) == 'db SELECT'
    assert query_span_name('DELETE', 'personas') == 'db DELETE personas'


def test_the_sql_state_is_the_code_only():
    class Wrapped(Exception):
        pass

    inner = DriverError('잔액이 user-0b9f5e0c 에 이미 있다', '23505')
    outer = Wrapped('감쌌다')
    outer.__cause__ = inner

    assert sql_state(outer) == '23505'
    assert sql_state(ConnectionError('끊겼다')) == 'error'
    assert sql_state(None) == 'error'


# 훅은 실행의 맥락(context)과 문장만 쓴다. 연결은 쓰지 않아 비워 넘기고, 맥락은 속성만 거는 빈 것이다
NO_CONNECTION = cast(Connection, None)


def blank_context() -> ExecutionContext:
    """속성만 걸 수 있는 빈 실행의 맥락."""
    return cast(ExecutionContext, SimpleNamespace())


def test_a_query_span_starts_and_ends_with_the_statement(spans: SpanRecorder):
    context = blank_context()
    with spans.parent():
        start_query_span(NO_CONNECTION, None, 'SELECT 1', None, context, False)
        end_query_span(NO_CONNECTION, None, 'SELECT 1', None, context, False)

    assert spans.names() == ['db SELECT']
    assert not hasattr(context, SPAN_ATTRIBUTE)


def test_a_failed_query_span_records_only_the_sql_state(spans: SpanRecorder):
    context = blank_context()
    error = DriverError('값 secret-0b9f 이 겹친다', '23505')
    failure = cast(ExceptionContext, SimpleNamespace(execution_context=context, original_exception=error))
    with spans.parent():
        start_query_span(NO_CONNECTION, None, 'INSERT INTO x VALUES (1)', None, context, False)
        fail_query_span(failure)
        # 실패를 적은 뒤에 끝을 알려 와도 두 번 끝내지 않는다
        end_query_span(NO_CONNECTION, None, '', None, context, False)

    span = spans.only()
    assert (span.status.status_code, span.status.description) == (StatusCode.ERROR, '23505')


def test_a_query_outside_a_span_gets_none(spans: SpanRecorder):
    start_query_span(NO_CONNECTION, None, 'SELECT 1', None, blank_context(), False)
    start_query_span(NO_CONNECTION, None, 'SELECT 1', None, None, False)

    assert spans.ended() == []


async def test_instrumenting_twice_attaches_once():
    engine = create_engine(make_test_settings())
    instrument_engine(engine)
    instrument_engine(engine)

    from sqlalchemy import event

    assert event.contains(engine.sync_engine, 'before_cursor_execute', start_query_span)
    await engine.dispose()


# --- 작업과 DB 의 메트릭 ---


def test_a_job_is_counted_until_it_ends(metrics: MetricsRecorder):
    labels = {'operation': 'test.job'}
    with measured_job('test.job'):
        assert metrics.value('background_jobs_running', **labels) == 1

    assert metrics.value('background_jobs_started', **labels) == 1
    assert metrics.value('background_jobs_finished', **labels, result='success') == 1
    assert metrics.value('background_job_duration', **labels) == 1


@pytest.mark.parametrize(('error', 'result'), [(RuntimeError, 'server_error'), (asyncio.CancelledError, 'cancelled')])
def test_a_job_that_raises_is_counted_by_how_it_ended(
    metrics: MetricsRecorder, error: type[BaseException], result: str
):
    with pytest.raises(error), measured_job('test.job'):
        raise error

    assert metrics.value('background_jobs_finished', operation='test.job', result=result) == 1
    assert metrics.value('background_jobs_running', operation='test.job') == 0


def test_the_database_state_and_the_pool_are_reported(metrics: MetricsRecorder, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(metrics_module, '_watched_pool', None)
    assert metrics.value('db_pool_connections_max') is None

    watch_pool(PoolStats(idle=lambda: 3, in_use=lambda: 2, maximum=15))
    record_db_up(False)
    record_pool_wait(0.002)

    assert metrics.value('db_up') == 0
    assert metrics.value('db_pool_connections', state='idle') == 3
    assert metrics.value('db_pool_connections', state='in_use') == 2
    assert metrics.value('db_pool_connections_max') == 15
    assert metrics.value('db_pool_wait') == 1


# --- 작업의 span ---


def test_a_failed_job_marks_its_span(spans: SpanRecorder):
    with pytest.raises(RuntimeError), job_span('test.job', 'job-12345'):
        raise RuntimeError('connect failed: postgresql+asyncpg://core:super-secret@db/trpg')

    span = spans.only()
    assert (span.status.status_code, span.status.description) == (StatusCode.ERROR, JOB_FAILED_ERROR_CODE)
    assert span.attributes['result'] == 'server_error'
    assert span.events == ()


def test_a_job_stopped_by_shutdown_is_not_an_error(spans: SpanRecorder):
    with pytest.raises(asyncio.CancelledError), job_span('test.job', 'job-12345'):
        raise asyncio.CancelledError

    span = spans.only()
    assert span.status.status_code != StatusCode.ERROR
    assert span.attributes['result'] == 'cancelled'


# --- 그 밖 ---


def test_the_current_trace_is_the_one_in_scope():
    trace = new_trace()
    assert current_trace() is None
    with request_scope('request-12345', trace):
        assert current_trace() == trace


def test_a_job_id_is_new_each_time():
    assert new_job_id() != new_job_id()


def test_whether_a_json_handler_is_attached():
    logger = logging.getLogger('tests.handlers')
    assert not has_json_handler(logger)
    handler = JsonLogHandler()
    logger.addHandler(handler)
    try:
        assert has_json_handler(logger)
    finally:
        logger.removeHandler(handler)


def test_a_malformed_traceparent_gives_no_parent():
    assert remote_parent('not-a-traceparent') is None
    assert remote_parent(None) is None


def test_tagging_a_span_carries_the_value(spans: SpanRecorder):
    with spans.parent(), job_span('test.job', 'job-1'):
        tag_current_span('request_id', 'request-12345')

    assert spans.only().attributes['request_id'] == 'request-12345'


def test_the_idle_filter_flushes_and_shuts_down_its_inner_processor():
    exporter = InMemorySpanExporter()
    processor = DropIdleRounds(SimpleSpanProcessor(exporter))

    assert processor.force_flush() is True
    processor.shutdown()
