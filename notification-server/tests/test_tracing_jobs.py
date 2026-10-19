# notification-server/tests/test_tracing_jobs.py

"""
작업 한 바퀴가 span 하나로 남는지 검증한다(app/observability/spans.py 의 job_span, app/notifications/retention.py).
식별자(context.py)가 span 을 따르는지도 본다.
"""

import asyncio
import logging

import pytest
from fastapi import FastAPI
from opentelemetry.trace import StatusCode, format_trace_id

from app.notifications.retention import PRUNE_OPERATION, NotificationPruner
from app.observability.context import current_ids, job_scope, outgoing_headers, request_scope
from app.observability.identifiers import new_trace
from app.observability.spans import ATTRIBUTE_JOB_ID, JOB_FAILED_ERROR_CODE, job_span, span_trace, span_traceparent
from tests.logs import rendered
from tests.spans import SpanRecorder, hex_span_id, hex_trace_id

pytestmark = pytest.mark.usefixtures('clean_tables')

LOGGER = 'app.notifications.retention'


def make_pruner(app: FastAPI) -> NotificationPruner:
    return NotificationPruner(session_factory=app.state.session_factory, retention_days=30)


async def test_a_round_is_a_span_of_its_own_trace(app: FastAPI, spans: SpanRecorder, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.DEBUG, logger=LOGGER), spans.parent() as parent:
        await make_pruner(app).tick()

    span = spans.find(PRUNE_OPERATION)
    # 띄운 곳의 span 아래에 놓이지 않는다. 한 시간마다 도는 것이 한 추적으로 묶이면 끝없이 길어진다
    assert span.parent is None
    assert span.context.trace_id != parent.get_span_context().trace_id
    (line,) = rendered(caplog.records, LOGGER)
    # 로그의 trace_id 와 job_id 가 이 span 의 것이다
    assert line['trace_id'] == hex_trace_id(span)
    assert span.attributes[ATTRIBUTE_JOB_ID] == line['job_id']
    assert span.attributes['result'] == 'success'


async def test_the_queries_of_a_round_sit_under_its_span(app: FastAPI, spans: SpanRecorder):
    await make_pruner(app).tick()

    round_span = spans.find(PRUNE_OPERATION)
    queries = [span for span in spans.ended() if span.name.startswith('db ')]
    assert queries
    assert all(query.parent.span_id == round_span.context.span_id for query in queries)


async def test_a_failed_round_marks_its_span(spans: SpanRecorder):
    with pytest.raises(RuntimeError), job_span(PRUNE_OPERATION, 'job-12345'):
        raise RuntimeError('connect failed: postgresql+asyncpg://notification:super-secret@db/trpg')

    span = spans.only()
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == JOB_FAILED_ERROR_CODE
    assert span.attributes['result'] == 'server_error'
    # 오류의 글은 로그에만 있다
    assert span.events == ()


async def test_a_round_stopped_by_shutdown_is_not_an_error(spans: SpanRecorder):
    with pytest.raises(asyncio.CancelledError), job_span(PRUNE_OPERATION, 'job-12345'):
        raise asyncio.CancelledError

    span = spans.only()
    assert span.status.status_code != StatusCode.ERROR
    assert span.attributes['result'] == 'cancelled'


async def test_without_tracing_a_round_still_gets_a_trace(app: FastAPI, caplog: pytest.LogCaptureFixture):
    # span 을 내보내지 않는 PC 에서는 지금처럼 새 추적을 만든다
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await make_pruner(app).tick()

    (line,) = rendered(caplog.records, LOGGER)
    assert len(line['trace_id']) == 32


def test_the_identifiers_follow_the_span(spans: SpanRecorder):
    with spans.parent() as parent:
        context = parent.get_span_context()
        trace_id = format_trace_id(context.trace_id)
        # 요청의 추적보다 span 이 앞선다. 받는 서버의 span 이 이 span 아래에 붙는다
        with request_scope('request-12345', new_trace()):
            expected = f'00-{trace_id}-{hex_span_id(context.span_id)}-{context.trace_flags:02x}'
            assert outgoing_headers() == {'traceparent': expected}
            assert span_traceparent() == expected
        # 요청 밖에서 시작한 작업은 span 의 추적을 쓴다
        with job_scope('job-12345'):
            assert current_ids()['trace_id'] == trace_id
        assert span_trace().trace_id == trace_id


def test_without_a_span_the_identifiers_are_unchanged():
    assert span_trace() is None
    assert span_traceparent() is None
    assert outgoing_headers() == {}
