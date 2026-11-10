# shared/server-core/tests/test_probes.py

"""
상태 확인 API(health.py 의 /health, readiness.py 의 /health/ready)를 검증한다.

DB 없이 돈다. 세션은 가짜를 넘기고 DB 에 닿아 보는 것(ping_database)을 바꿔 끼운다.
실제 DB 에 닿는 것(연결 거부, 비밀번호가 로그에 남지 않는 것)은 서버마다의 tests/test_readiness.py 가 본다.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.exc import OperationalError

from server_core import health, readiness
from server_core.database import get_session
from server_core.testing.metrics import MetricsRecorder
from tests.conftest import make_client


async def fake_session() -> AsyncIterator[object]:
    """요청마다의 세션 대신 넘기는 것. ping_database 를 바꿔 끼우므로 쓰이지 않는다."""
    yield object()


@pytest.fixture
async def probe_client() -> AsyncIterator[AsyncClient]:
    """두 라우터만 붙인 작은 앱에 요청을 보내는 클라이언트."""
    app = FastAPI()
    app.include_router(health.router)
    app.include_router(readiness.router)
    app.dependency_overrides[get_session] = fake_session
    async with make_client(app) as client:
        yield client


@pytest.fixture
def reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB 에 닿는 것으로 한다."""

    async def answer(session) -> None:
        return None

    monkeypatch.setattr(readiness, 'ping_database', answer)


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
async def test_health_is_ok_without_looking_at_the_database(probe_client: AsyncClient, method: str):
    response = await probe_client.request(method, '/health')

    assert response.status_code == status.HTTP_200_OK
    assert response.content == (b'{"status":"ok"}' if method == 'GET' else b'')


@pytest.mark.usefixtures('reachable')
async def test_ready_when_the_database_answers(probe_client: AsyncClient, metrics: MetricsRecorder):
    response = await probe_client.get('/health/ready')

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok'}
    assert metrics.value('db_up') == 1


@pytest.mark.usefixtures('reachable')
async def test_ready_answers_head_without_a_body(probe_client: AsyncClient):
    response = await probe_client.head('/health/ready')

    assert response.status_code == status.HTTP_200_OK
    assert response.content == b''


@pytest.mark.parametrize(
    'error',
    [OperationalError('SELECT 1', {}, Exception('password=secret')), ConnectionRefusedError('password=secret')],
)
async def test_not_ready_when_the_database_fails(
    monkeypatch: pytest.MonkeyPatch,
    probe_client: AsyncClient,
    metrics: MetricsRecorder,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
):
    async def fail(session) -> None:
        raise error

    monkeypatch.setattr(readiness, 'ping_database', fail)

    with caplog.at_level(logging.WARNING, logger=readiness.__name__):
        response = await probe_client.get('/health/ready')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    # 원인은 응답에 싣지 않는다
    assert response.json() == {'status': 'unavailable'}
    assert metrics.value('db_up') == 0
    # 로그에는 오류의 종류만 남는다. 오류의 글(주소, 계정)은 남지 않는다
    assert f'DB 에 닿지 않는다({type(error).__name__})' in caplog.text
    assert 'secret' not in caplog.text


async def test_not_ready_when_the_database_does_not_answer_in_time(
    monkeypatch: pytest.MonkeyPatch, probe_client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    async def hang(session) -> None:
        await asyncio.sleep(10)

    monkeypatch.setattr(readiness, 'ping_database', hang)
    monkeypatch.setattr(readiness, 'READINESS_TIMEOUT_SECONDS', 0.05)

    with caplog.at_level(logging.WARNING, logger=readiness.__name__):
        response = await probe_client.get('/health/ready')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {'status': 'unavailable'}
    assert '0.05초 안에 확인이 끝나지 않았다' in caplog.text


def test_the_docs_list_each_probe_once_without_head():
    app = FastAPI()
    app.include_router(health.router)
    app.include_router(readiness.router)

    paths = app.openapi()['paths']

    assert {path: sorted(methods) for path, methods in paths.items()} == {
        '/health': ['get'],
        '/health/ready': ['get'],
    }
    assert paths['/health']['get']['operationId'] == 'check_health_health_get'
    assert paths['/health/ready']['get']['operationId'] == 'check_readiness_health_ready_get'
