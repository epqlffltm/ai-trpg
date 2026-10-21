# asset-server/tests/test_metrics.py

"""
메트릭을 세는 곳을 검증한다. 이름, 단위, label 이 docs/observability.md 의 "메트릭"의 표와 같은지 본다.
server_core/observability/metrics.py, request_metrics.py, pool_metrics.py 와,
그것을 부르는 readiness, 뒤의 작업(tests/jobs.py).
메모리에 모으는 것(server_core/testing/metrics.py)으로 읽는다.
끝에서 끝까지(Prometheus 에 들어오는가)는 CI 의 stack 이 본다.
"""

import asyncio

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.database import POOL_MAX_CONNECTIONS
from server_core.observability import metrics as metrics_module
from server_core.observability.metrics import (
    DURATION_BUCKETS,
    OTHER_METHOD,
    method_label,
    observe_pool_connections,
    record_request,
)
from server_core.observability.pool_metrics import MeteredPool
from server_core.observability.request_metrics import RequestMetricsMiddleware
from server_core.testing.metrics import MetricsRecorder
from sqlalchemy import text

from app.api import readiness
from tests.jobs import PROBE_OPERATION, run_round
from tests.probes import PROBE_ROUTE, add_probe_route

# 토큰이 있어야 하는 주소. 토큰 없이 부르면 401 이다
ME = '/api/v1/asset/me'


async def test_a_request_is_counted_by_method_route_and_status(client: AsyncClient, metrics: MetricsRecorder):
    await client.get(ME)

    labels = {'method': 'GET', 'route': ME}
    assert metrics.value('http_server_requests', **labels, status_code=401) == 1
    assert metrics.value('http_server_request_duration', **labels) == 1
    # 끝난 요청은 처리 중인 수에서 빠진다
    assert metrics.value('http_server_active_requests') == 0


async def test_the_route_is_the_template_and_unmatched_is_one_label(
    app: FastAPI, client: AsyncClient, metrics: MetricsRecorder
):
    add_probe_route(app)
    await client.post('/api/v1/asset/probes/12345/read')
    await client.get('/no/such/secret-path')

    routes = {point.labels['route'] for point in metrics.points('http_server_requests')}
    assert routes == {PROBE_ROUTE, '(unmatched)'}


def test_an_unknown_method_is_one_label():
    assert method_label('GET') == 'GET'
    assert method_label('BREW') == OTHER_METHOD


async def test_the_duration_is_in_seconds_with_the_shared_buckets(client: AsyncClient, metrics: MetricsRecorder):
    await client.get('/health')

    (point,) = metrics.points('http_server_request_duration')
    assert point.unit == 's'
    data = metrics.reader.get_metrics_data()
    histogram = next(
        metric.data.data_points[0]
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == 'http_server_request_duration'
    )
    assert tuple(histogram.explicit_bounds) == DURATION_BUCKETS


async def test_a_request_that_raises_is_counted_as_500(metrics: MetricsRecorder):
    async def broken(scope, receive, send) -> None:
        raise RuntimeError('부서졌다')

    with pytest.raises(RuntimeError):
        await RequestMetricsMiddleware(broken)({'type': 'http', 'method': 'GET', 'path': '/x'}, None, None)

    assert metrics.value('http_server_requests', status_code=500) == 1
    assert metrics.value('http_server_active_requests') == 0


async def test_a_scope_that_is_not_http_is_not_counted(metrics: MetricsRecorder):
    seen: list[dict] = []

    async def inner(scope, receive, send) -> None:
        seen.append(scope)

    await RequestMetricsMiddleware(inner)({'type': 'lifespan'}, None, None)

    assert seen == [{'type': 'lifespan'}]
    assert metrics.points('http_server_requests') == []


def test_recording_without_a_provider_does_nothing():
    # 끼운 것이 없으면(NoOp) 세어도 아무 일이 없다. 테스트가 아닌 PC 에서 띄운 서버와 같다
    record_request('GET', '/health', 200, 0.01)


async def test_readiness_records_the_database_state(
    client: AsyncClient, metrics: MetricsRecorder, monkeypatch: pytest.MonkeyPatch
):
    await client.get('/health/ready')
    assert metrics.value('db_up') == 1

    async def unreachable(session) -> str:
        return 'DB 에 닿지 않는다(OSError)'

    monkeypatch.setattr(readiness, 'find_problem', unreachable)
    response = await client.get('/health/ready')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert metrics.value('db_up') == 0


async def test_the_pool_reports_its_connections_and_waits(app: FastAPI, metrics: MetricsRecorder):
    async with app.state.engine.connect() as connection:
        await connection.execute(text('SELECT 1'))
        in_use = metrics.value('db_pool_connections', state='in_use')

    assert in_use is not None and in_use >= 1
    assert metrics.value('db_pool_connections', state='idle') is not None
    assert metrics.value('db_pool_connections_max') == POOL_MAX_CONNECTIONS
    (wait,) = metrics.points('db_pool_wait')
    assert (wait.unit, wait.value >= 1) == ('s', True)


def test_without_a_watched_pool_there_are_no_connections(monkeypatch: pytest.MonkeyPatch):
    # 앱이 뜨기 전에 수집이 돌면 지켜보는 풀이 없다
    monkeypatch.setattr(metrics_module, '_watched_pool', None)

    assert list(observe_pool_connections(None)) == []


def test_the_engine_uses_the_metered_pool(app: FastAPI):
    # SQLAlchemy 의 안쪽 이름(_do_get)을 감싼다. 판이 바뀌어 이름이 사라지면 여기서 안다
    assert isinstance(app.state.engine.sync_engine.pool, MeteredPool)
    assert callable(getattr(super(MeteredPool, app.state.engine.sync_engine.pool), '_do_get', None))


async def test_a_round_is_counted_as_a_job(app: FastAPI, metrics: MetricsRecorder):
    await run_round(app)

    labels = {'operation': PROBE_OPERATION}
    assert metrics.value('background_jobs_started', **labels) == 1
    assert metrics.value('background_jobs_finished', **labels, result='success') == 1
    assert metrics.value('background_jobs_running', **labels) == 0
    assert metrics.value('background_job_duration', **labels) == 1


async def test_a_failed_round_is_a_server_error(app: FastAPI, metrics: MetricsRecorder):
    async def broken(app: FastAPI) -> None:
        raise RuntimeError('DB 가 없다')

    with pytest.raises(RuntimeError):
        await run_round(app, broken)

    assert metrics.value('background_jobs_finished', operation=PROBE_OPERATION, result='server_error') == 1
    assert metrics.value('background_jobs_running', operation=PROBE_OPERATION) == 0


async def test_a_round_stopped_by_shutdown_is_cancelled(app: FastAPI, metrics: MetricsRecorder):
    async def stopped(app: FastAPI) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_round(app, stopped)

    assert metrics.value('background_jobs_finished', operation=PROBE_OPERATION, result='cancelled') == 1
