# asset-server/tests/test_readiness.py

"""
서버가 요청을 처리할 준비가 됐는지 묻는 API(/health/ready)를 검증한다.

DB 에 닿으면 200, 닿지 않거나 3초 안에 답이 없으면 503 이다. 응답에는 원인을 싣지 않는다.
"""

import asyncio
import logging

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.api import readiness
from app.core.database import create_engine
from app.main import create_app
from tests.conftest import make_client, make_test_settings

# 아무것도 듣지 않는 포트. 연결이 바로 거부된다
CLOSED_PORT_URL = 'postgresql+asyncpg://asset:wrong-password@127.0.0.1:1/trpg'


async def test_ready_when_the_database_answers(client: AsyncClient):
    response = await client.get('/health/ready')

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok'}


async def test_ready_answers_head_without_a_body(client: AsyncClient):
    response = await client.head('/health/ready')

    assert response.status_code == status.HTTP_200_OK
    assert response.content == b''


async def test_not_ready_when_the_database_is_unreachable(caplog: pytest.LogCaptureFixture):
    settings = make_test_settings(database_url=CLOSED_PORT_URL)
    engine = create_engine(settings)
    app = create_app(settings, engine=engine)

    with caplog.at_level(logging.WARNING, logger=readiness.__name__):
        async with make_client(app) as client:
            response = await client.get('/health/ready')
    await engine.dispose()

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    # 주소, 계정, 오류 문구를 응답에 싣지 않는다
    assert response.json() == {'status': 'unavailable'}
    # 로그에는 오류의 종류만 남는다. 비밀번호가 든 주소는 남지 않는다
    assert 'wrong-password' not in caplog.text
    assert 'DB 에 닿지 않는다' in caplog.text


async def test_not_ready_when_the_database_does_not_answer_in_time(
    monkeypatch: pytest.MonkeyPatch, app: FastAPI, client: AsyncClient
):
    async def hang(session) -> None:
        await asyncio.sleep(10)

    monkeypatch.setattr(readiness, 'ping_database', hang)
    monkeypatch.setattr(readiness, 'READINESS_TIMEOUT_SECONDS', 0.05)

    response = await client.get('/health/ready')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {'status': 'unavailable'}
