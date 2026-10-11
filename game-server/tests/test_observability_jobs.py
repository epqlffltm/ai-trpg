# game-server/tests/test_observability_jobs.py

"""
뒤에서 도는 작업에 식별자(job_id)가 걸리는지, 우리 서버를 부를 때 추적이 이어지는지 검증한다
(app/core/jobs.py, app/observability/context.py). 규격은 docs/observability.md 에 있다.
"""

import asyncio
import logging
import uuid

import httpx
import pytest

from app.auth.jwks import fetch_jwks
from app.core.jobs import BackgroundJobs
from app.observability.context import current_ids, request_scope
from app.observability.identifiers import new_trace, parse_traceparent
from tests.logs import rendered
from tests.signing import FakeAuthServer

JOBS_LOGGER = 'app.core.jobs'
JWKS_URL = 'http://auth.test/api/v1/auth/jwks'


def job_lines(caplog: pytest.LogCaptureFixture) -> list[dict]:
    """작업을 돌리는 곳이 남긴 줄들."""
    return rendered(caplog.records, JOBS_LOGGER)


async def test_a_job_gets_its_own_id():
    jobs = BackgroundJobs()
    seen: dict[str, str] = {}

    async def job() -> None:
        seen.update(current_ids())

    job_id = jobs.spawn(job(), name='narrate:테이블:1', operation='round.narrate')
    await jobs.drain()

    assert str(uuid.UUID(job_id)) == job_id
    assert seen['job_id'] == job_id


async def test_every_job_gets_a_different_id():
    jobs = BackgroundJobs()

    async def job() -> None:
        return None

    first = jobs.spawn(job(), name='첫째')
    second = jobs.spawn(job(), name='둘째')
    await jobs.drain()

    assert first != second


async def test_a_job_does_not_carry_the_request_id_of_the_request_that_started_it():
    jobs = BackgroundJobs()
    trace = new_trace()
    seen: dict[str, str] = {}

    async def job() -> None:
        seen.update(current_ids())

    with request_scope('request-12345', trace):
        jobs.spawn(job(), name='narrate:테이블:1', operation='round.narrate')
    await jobs.drain()

    # 작업은 요청이 끝난 뒤에도 돈다. 요청의 식별자가 아니라 제 식별자를 쓴다
    assert 'request_id' not in seen
    # 어느 요청에서 비롯됐는지는 추적으로 잇는다
    assert seen['trace_id'] == trace.trace_id


async def test_spawning_inside_a_request_leaves_a_line_linking_the_two(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs()

    async def job() -> None:
        return None

    with caplog.at_level(logging.INFO, logger=JOBS_LOGGER), request_scope('request-12345', new_trace()):
        job_id = jobs.spawn(job(), name='index-lore:판', operation='lore.index')
    await jobs.drain()

    spawned = job_lines(caplog)[0]
    # 요청의 기록에서 작업의 기록으로 넘어가는 고리다
    assert spawned['request_id'] == 'request-12345'
    assert spawned['spawned_job_id'] == job_id
    assert spawned['operation'] == 'lore.index'


async def test_a_finished_job_leaves_a_line_with_the_common_fields(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs()

    async def job() -> None:
        return None

    with caplog.at_level(logging.INFO, logger=JOBS_LOGGER):
        job_id = jobs.spawn(job(), name='narrate:테이블:1', operation='round.narrate')
        await jobs.drain()

    (finished,) = [line for line in job_lines(caplog) if line.get('result') == 'success']
    assert finished['job_id'] == job_id
    assert finished['operation'] == 'round.narrate'
    assert finished['job_name'] == 'narrate:테이블:1'
    assert finished['level'] == 'info'
    assert isinstance(finished['duration_ms'], int)
    assert 'request_id' not in finished


async def test_a_failed_job_can_be_traced_by_its_id(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs()

    async def job() -> None:
        raise RuntimeError('서술자가 죽었다')

    with caplog.at_level(logging.INFO, logger=JOBS_LOGGER):
        job_id = jobs.spawn(job(), name='narrate:테이블:1', operation='round.narrate')
        await jobs.drain()

    (failed,) = [line for line in job_lines(caplog) if line['level'] == 'error']
    assert failed['job_id'] == job_id
    assert failed['operation'] == 'round.narrate'
    assert failed['result'] == 'server_error'
    assert failed['error_code'] == 'job.failed'
    assert failed['error_type'] == 'RuntimeError'
    assert 'RuntimeError: 서술자가 죽었다' in failed['stack_trace']


async def test_logs_inside_a_job_carry_its_id(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs()
    inner = logging.getLogger('tests.inside-a-job')

    async def job() -> None:
        inner.warning('찾는 글을 벡터로 바꾸지 못했다')

    with caplog.at_level(logging.WARNING, logger=inner.name):
        job_id = jobs.spawn(job(), name='index-memories:테이블', operation='memory.index')
        await jobs.drain()

    (line,) = rendered(caplog.records, inner.name)
    assert line['job_id'] == job_id


async def test_a_cancelled_job_is_logged_as_cancelled(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs()

    async def endless() -> None:
        await asyncio_forever()

    with caplog.at_level(logging.INFO, logger=JOBS_LOGGER):
        job_id = jobs.spawn(endless(), name='끝나지 않는 작업')
        await jobs.aclose(grace=0.01)

    (cancelled,) = [line for line in job_lines(caplog) if line.get('result') == 'cancelled']
    assert cancelled['job_id'] == job_id
    assert cancelled['level'] == 'warning'


async def test_a_job_started_by_another_job_is_linked_to_it(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs()
    spawned: list[str] = []

    async def child() -> None:
        return None

    async def parent() -> None:
        spawned.append(jobs.spawn(child(), name='자식'))

    with caplog.at_level(logging.INFO, logger=JOBS_LOGGER):
        parent_id = jobs.spawn(parent(), name='부모')
        await jobs.drain()

    (link,) = [line for line in job_lines(caplog) if line.get('spawned_job_id') == spawned[0]]
    # 맡긴 쪽이 작업이면 그 작업의 식별자가 붙는다
    assert link['job_id'] == parent_id


async def asyncio_forever() -> None:
    """끝나지 않는다. 취소될 때까지 기다린다."""
    await asyncio.Event().wait()


async def test_calling_the_auth_server_carries_the_trace_on(auth_server: FakeAuthServer):
    received: list[httpx.Request] = []

    async def record(request: httpx.Request) -> None:
        received.append(request)

    trace = new_trace()
    async with auth_server.make_client() as client:
        client.event_hooks['request'].append(record)
        with request_scope('request-12345', trace):
            await fetch_jwks(client, JWKS_URL)

    (request,) = received
    assert parse_traceparent(request.headers['traceparent']) == trace
    # 요청의 식별자는 넘기지 않는다. 받는 서버가 제 것을 만든다
    assert 'x-request-id' not in request.headers


async def test_calling_the_auth_server_outside_a_request_sends_no_trace(auth_server: FakeAuthServer):
    received: list[httpx.Request] = []

    async def record(request: httpx.Request) -> None:
        received.append(request)

    async with auth_server.make_client() as client:
        client.event_hooks['request'].append(record)
        await fetch_jwks(client, JWKS_URL)

    assert 'traceparent' not in received[0].headers
