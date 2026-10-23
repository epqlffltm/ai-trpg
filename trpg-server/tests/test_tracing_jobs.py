# trpg-server/tests/test_tracing_jobs.py

"""
작업 하나(또는 정리 작업의 한 바퀴)가 span 하나로 남는지 검증한다.
server_core/observability/spans.py 의 job_span, app/core/jobs.py 의 BackgroundJobs,
정리 작업의 한 바퀴(app/ai_log/retention.py).
식별자(context.py)가 span 을 따르는지도 본다.
"""

import asyncio
import logging

import pytest
from fastapi import FastAPI
from opentelemetry.trace import StatusCode, format_trace_id
from server_core.observability.context import current_ids, job_scope, outgoing_headers, request_scope
from server_core.observability.identifiers import new_trace
from server_core.observability.spans import (
    ATTRIBUTE_JOB_ID,
    JOB_FAILED_ERROR_CODE,
    job_span,
    span_trace,
    span_traceparent,
)
from server_core.testing.logs import rendered
from server_core.testing.spans import SpanRecorder, hex_span_id, hex_trace_id

from app.ai_log.retention import PRUNE_OPERATION, AiLogPruner
from app.core.jobs import BackgroundJobs

JOBS_LOGGER = 'app.core.jobs'
RETENTION_LOGGER = 'app.ai_log.retention'
NARRATE = 'round.narrate'


async def test_a_spawned_job_sits_under_the_span_that_spawned_it(spans: SpanRecorder, caplog: pytest.LogCaptureFixture):
    # 요청이 맡긴 서술은 그 요청의 추적에 이어진다. 요청이 끝난 뒤에도 돈다
    jobs = BackgroundJobs()
    seen: dict[str, str] = {}

    async def narrate() -> None:
        seen.update(current_ids())

    with caplog.at_level(logging.INFO, logger=JOBS_LOGGER):
        with spans.parent() as parent, request_scope('request-12345', span_trace()):
            job_id = jobs.spawn(narrate(), 'narrate:table:1', NARRATE)
        await jobs.drain()

    span = spans.find(NARRATE)
    assert span.parent.span_id == parent.get_span_context().span_id
    assert span.attributes[ATTRIBUTE_JOB_ID] == job_id
    assert span.attributes['result'] == 'success'
    # 작업 안의 로그가 같은 추적과 그 작업의 번호를 단다
    assert seen['trace_id'] == hex_trace_id(span)
    assert seen['job_id'] == job_id
    finished = [line for line in rendered(caplog.records, JOBS_LOGGER) if line.get('result') == 'success']
    assert finished[0]['trace_id'] == hex_trace_id(span)


async def test_a_failed_job_marks_its_span(spans: SpanRecorder):
    jobs = BackgroundJobs()

    async def narrate() -> None:
        raise RuntimeError('connect failed: postgresql+asyncpg://game:super-secret@db/trpg')

    jobs.spawn(narrate(), 'narrate:table:1', NARRATE)
    await jobs.drain()

    span = spans.find(NARRATE)
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == JOB_FAILED_ERROR_CODE
    assert span.attributes['result'] == 'server_error'
    # 오류의 글은 로그에만 있다
    assert span.events == ()


async def test_a_job_stopped_by_shutdown_is_not_an_error(spans: SpanRecorder):
    jobs = BackgroundJobs()
    started = asyncio.Event()

    async def narrate() -> None:
        started.set()
        await asyncio.sleep(60)

    jobs.spawn(narrate(), 'narrate:table:1', NARRATE)
    await started.wait()
    await jobs.aclose(grace=0)

    span = spans.find(NARRATE)
    assert span.status.status_code != StatusCode.ERROR
    assert span.attributes['result'] == 'cancelled'


@pytest.mark.usefixtures('clean_tables')
async def test_a_round_of_a_loop_is_a_new_trace_with_its_queries(
    app: FastAPI, spans: SpanRecorder, caplog: pytest.LogCaptureFixture
):
    # 서버가 뜰 때 시작한 정리 작업에는 걸린 span 이 없다. 바퀴마다 새 추적이다
    with caplog.at_level(logging.DEBUG, logger=RETENTION_LOGGER):
        await AiLogPruner(app.state.session_factory, 30).tick()

    span = spans.find(PRUNE_OPERATION)
    assert span.parent is None
    (line,) = rendered(caplog.records, RETENTION_LOGGER)
    assert line['trace_id'] == hex_trace_id(span)
    assert span.attributes[ATTRIBUTE_JOB_ID] == line['job_id']
    queries = [query for query in spans.ended() if query.name.startswith('db ')]
    assert queries
    assert all(query.parent.span_id == span.context.span_id for query in queries)


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


def test_without_a_span_the_identifiers_are_unchanged():
    assert span_trace() is None
    assert span_traceparent() is None
    assert outgoing_headers() == {}


async def test_job_span_alone_marks_success_and_failure(spans: SpanRecorder):
    with job_span('charge.settle', 'job-1'):
        pass
    with pytest.raises(ValueError), job_span('charge.settle', 'job-2'):
        raise ValueError('틀렸다')

    first, second = spans.ended()
    assert first.attributes['result'] == 'success'
    assert second.attributes['result'] == 'server_error'
