# notification-server/tests/test_metrics.py

"""
메트릭을 세는 곳을 검증한다. 이름, 단위, label 이 docs/observability.md 의 "메트릭"의 표와 같은지 본다.
app/observability/metrics.py, request_metrics.py, pool_metrics.py 와, 그것을 부르는 readiness, 정리 작업, 알림 넣기.
메모리에 모으는 것(tests/metrics.py)으로 읽는다. 끝에서 끝까지(Prometheus 에 들어오는가)는 CI 의 stack 이 본다.
"""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text

from app.api import readiness
from app.core.database import POOL_MAX_CONNECTIONS
from app.notifications.retention import PRUNE_OPERATION, NotificationPruner
from app.observability.metrics import DURATION_BUCKETS, OTHER_METHOD, method_label, record_request
from app.observability.pool_metrics import MeteredPool
from app.observability.request_metrics import RequestMetricsMiddleware
from tests.metrics import MetricsRecorder
from tests.signing import signed_put

USER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b'
INBOX = '/api/v1/notification/me/notifications'
RETIRING = {
    'table_id': '9d1c2b3a-4e5f-4a6b-8c7d-0e1f2a3b4c5d',
    'title': '잊힌 탑',
    'narration_model': 'model-a',
    'retires_on': '2026-11-01',
    'days_left': 12,
}


def retiring(key: str = 'narration-model-retiring:1', **payload: object) -> dict:
    """게임 서버가 넣는 은퇴 알림."""
    return {
        'source_key': key,
        'user_id': USER,
        'kind': 'narration_model.retiring',
        'payload': {**RETIRING, **payload},
    }


async def test_a_request_is_counted_by_method_route_and_status(client: AsyncClient, metrics: MetricsRecorder):
    await client.get(INBOX)

    labels = {'method': 'GET', 'route': INBOX}
    assert metrics.value('http_server_requests', **labels, status_code=401) == 1
    assert metrics.value('http_server_request_duration', **labels) == 1
    # 끝난 요청은 처리 중인 수에서 빠진다
    assert metrics.value('http_server_active_requests') == 0


async def test_the_route_is_the_template_and_unmatched_is_one_label(client: AsyncClient, metrics: MetricsRecorder):
    await client.post('/api/v1/notification/me/notifications/12345/read')
    await client.get('/no/such/secret-path')

    routes = {point.labels['route'] for point in metrics.points('http_server_requests')}
    assert routes == {'/api/v1/notification/me/notifications/{notification_id}/read', '(unmatched)'}


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


def test_the_engine_uses_the_metered_pool(app: FastAPI):
    # SQLAlchemy 의 안쪽 이름(_do_get)을 감싼다. 판이 바뀌어 이름이 사라지면 여기서 안다
    assert isinstance(app.state.engine.sync_engine.pool, MeteredPool)
    assert callable(getattr(super(MeteredPool, app.state.engine.sync_engine.pool), '_do_get', None))


def make_pruner(app: FastAPI) -> NotificationPruner:
    return NotificationPruner(
        session_factory=app.state.session_factory, retention_days=30, clock=lambda: datetime(2026, 10, 20, tzinfo=UTC)
    )


@pytest.mark.usefixtures('clean_tables')
async def test_a_prune_round_is_counted_as_a_job(app: FastAPI, metrics: MetricsRecorder):
    await make_pruner(app).tick()

    labels = {'operation': PRUNE_OPERATION}
    assert metrics.value('background_jobs_started', **labels) == 1
    assert metrics.value('background_jobs_finished', **labels, result='success') == 1
    assert metrics.value('background_jobs_running', **labels) == 0
    assert metrics.value('background_job_duration', **labels) == 1


async def test_a_failed_round_is_a_server_error(
    app: FastAPI, metrics: MetricsRecorder, monkeypatch: pytest.MonkeyPatch
):
    async def broken(self) -> int:
        raise RuntimeError('DB 가 없다')

    monkeypatch.setattr(NotificationPruner, 'sweep', broken)
    with pytest.raises(RuntimeError):
        await make_pruner(app).tick()

    assert metrics.value('background_jobs_finished', operation=PRUNE_OPERATION, result='server_error') == 1
    assert metrics.value('background_jobs_running', operation=PRUNE_OPERATION) == 0


async def test_a_round_stopped_by_shutdown_is_cancelled(
    app: FastAPI, metrics: MetricsRecorder, monkeypatch: pytest.MonkeyPatch
):
    async def stopped(self) -> int:
        raise asyncio.CancelledError

    monkeypatch.setattr(NotificationPruner, 'sweep', stopped)
    with pytest.raises(asyncio.CancelledError):
        await make_pruner(app).tick()

    assert metrics.value('background_jobs_finished', operation=PRUNE_OPERATION, result='cancelled') == 1


@pytest.mark.usefixtures('clean_tables')
async def test_put_notifications_are_counted_by_source_and_outcome(client: AsyncClient, metrics: MetricsRecorder):
    await signed_put(client, retiring())
    await signed_put(client, retiring())
    await signed_put(client, retiring(days_left=3))
    await signed_put(client, {**retiring('k:2'), 'kind': 'order.paid'})

    assert metrics.value('notifications_received', source='game', outcome='created') == 1
    assert metrics.value('notifications_received', source='game', outcome='existing') == 1
    assert metrics.value('notifications_received', source='game', outcome='conflict') == 1
    assert metrics.value('notifications_received', source='game', outcome='refused') == 1


async def test_an_unsigned_put_is_not_counted(client: AsyncClient, metrics: MetricsRecorder):
    await signed_put(client, retiring(), secret='x' * 40)
    await client.post('/api/v1/notification/service/made-up/notifications', content=b'{}')

    assert metrics.points('notifications_received') == []
