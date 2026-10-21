# asset-server/tests/test_health.py

"""
서버가 살아 있는지 묻는 API(/health)와 API 문서의 공개 범위를 검증한다.
"""

import asyncio

from fastapi import status
from httpx import AsyncClient
from server_core.database import create_engine
from server_core.testing.tokens import TEST_USER_ID, FakeAuthServer, revoked_entry
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import API_PREFIX, create_app
from tests.conftest import make_client, make_test_settings


async def test_health_answers_ok(client: AsyncClient):
    response = await client.get('/health')

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok'}


async def test_health_answers_head_without_a_body(client: AsyncClient):
    response = await client.head('/health')

    assert response.status_code == status.HTTP_200_OK
    assert response.content == b''


async def test_the_api_docs_are_closed_by_default(client: AsyncClient):
    # 운영 서버에서는 API 의 구조를 내보이지 않는다
    for path in (f'{API_PREFIX}/docs', f'{API_PREFIX}/openapi.json'):
        response = await client.get(path)

        assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_the_api_docs_open_in_debug(engine: AsyncEngine):
    app = create_app(make_test_settings(debug=True), engine=engine)

    async with make_client(app) as client:
        response = await client.get(f'{API_PREFIX}/openapi.json')

    assert response.status_code == status.HTTP_200_OK
    # HEAD 는 문서에 올리지 않는다. GET 하나만 있다
    assert list(response.json()['paths']['/health']) == ['get']


async def test_starting_and_shutting_down(auth_server: FakeAuthServer):
    """
    뜰 때 뒤의 작업(끊긴 세션 목록 받기)이 돌고, 꺼질 때 멈추고 연결을 닫는다.

    닫지 않으면 DB 와 인증 서버 쪽에 끊긴 연결이 한동안 남는다.
    """
    settings = make_test_settings()
    engine = create_engine(settings)
    app = create_app(settings, http_client=auth_server.make_client(), engine=engine)
    auth_server.revocations = [revoked_entry(str(TEST_USER_ID), 1)]

    async with app.router.lifespan_context(app), make_client(app) as client:
        assert (await client.get('/health/ready')).status_code == status.HTTP_200_OK
        # 뜨자마자 목록을 받는다
        for _ in range(50):
            if app.state.revocations.is_revoked(str(TEST_USER_ID), 0):
                break
            await asyncio.sleep(0.01)
        assert app.state.revocations.is_revoked(str(TEST_USER_ID), 0)
        assert engine.pool.checkedin() >= 1

    # 풀을 닫으면 쉬고 있던 연결이 모두 끊긴다. 인증 서버로 가는 클라이언트도 닫힌다
    assert engine.pool.checkedin() == 0
    assert app.state.http_client.is_closed
