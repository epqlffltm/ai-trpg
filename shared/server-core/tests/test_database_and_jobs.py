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

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from server_core.database import (
    MAX_OVERFLOW,
    POOL_MAX_CONNECTIONS,
    POOL_SIZE,
    create_engine,
    create_session_factory,
    get_session,
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
    engine = create_engine(make_test_settings(), pool_size=2, max_overflow=1)

    pool = engine.sync_engine.pool
    assert isinstance(pool, MeteredPool)
    assert (pool.size(), pool._max_overflow) == (2, 1)
    stats = pool_stats(engine, 3)
    assert (stats.idle(), stats.in_use(), stats.maximum) == (0, 0, 3)
    await engine.dispose()


def test_the_default_pool_matches_the_metric():
    assert POOL_MAX_CONNECTIONS == POOL_SIZE + MAX_OVERFLOW


async def test_a_request_gets_a_session_from_the_app():
    engine = create_engine(make_test_settings())
    factory = create_session_factory(engine, info={'signer': 'test'})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_factory=factory)))

    sessions = get_session(request)
    session = await anext(sessions)
    assert session.info == {'signer': 'test'}
    await sessions.aclose()
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

    inner = Exception('잔액이 user-0b9f5e0c 에 이미 있다')
    inner.sqlstate = '23505'
    outer = Wrapped('감쌌다')
    outer.__cause__ = inner

    assert sql_state(outer) == '23505'
    assert sql_state(ConnectionError('끊겼다')) == 'error'
    assert sql_state(None) == 'error'


def test_a_query_span_starts_and_ends_with_the_statement(spans: SpanRecorder):
    context = SimpleNamespace()
    with spans.parent():
        start_query_span(None, None, 'SELECT 1', None, context, False)
        end_query_span(None, None, 'SELECT 1', None, context, False)

    assert spans.names() == ['db SELECT']
    assert not hasattr(context, SPAN_ATTRIBUTE)


def test_a_failed_query_span_records_only_the_sql_state(spans: SpanRecorder):
    context = SimpleNamespace()
    error = Exception('값 secret-0b9f 이 겹친다')
    error.sqlstate = '23505'
    with spans.parent():
        start_query_span(None, None, 'INSERT INTO x VALUES (1)', None, context, False)
        fail_query_span(SimpleNamespace(execution_context=context, original_exception=error))
        # 실패를 적은 뒤에 끝을 알려 와도 두 번 끝내지 않는다
        end_query_span(None, None, '', None, context, False)

    span = spans.only()
    assert (span.status.status_code, span.status.description) == (StatusCode.ERROR, '23505')


def test_a_query_outside_a_span_gets_none(spans: SpanRecorder):
    start_query_span(None, None, 'SELECT 1', None, SimpleNamespace(), False)
    start_query_span(None, None, 'SELECT 1', None, None, False)

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
def test_a_job_that_raises_is_counted_by_how_it_ended(metrics: MetricsRecorder, error: type, result: str):
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
