# game-server/tests/test_readiness.py

"""
서버가 요청을 처리할 준비가 됐는지 확인하는 API 를 검증한다.
"""

import logging

import pytest
from fastapi import status
from httpx import AsyncClient

from app.main import create_app
from tests.conftest import make_client, make_test_settings
from tests.logs import rendered
from tests.test_health import UNREACHABLE_DATABASE_URL


async def test_ready_returns_ok_when_the_database_answers(client: AsyncClient):
    response = await client.get('/health/ready')

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok'}


async def test_ready_returns_503_when_the_database_is_unreachable():
    app = create_app(make_test_settings(database_url=UNREACHABLE_DATABASE_URL))

    async with make_client(app) as client:
        response = await client.get('/health/ready')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {'status': 'unavailable'}


async def test_ready_does_not_reveal_why_it_failed():
    app = create_app(make_test_settings(database_url=UNREACHABLE_DATABASE_URL))

    async with make_client(app) as client:
        response = await client.get('/health/ready')

    # 오류 문구에는 DB 주소와 계정 이름이 들어 있다. 응답에 싣지 않는다
    assert '127.0.0.1' not in response.text
    assert 'game' not in response.text


async def test_ready_answers_head_like_get(client: AsyncClient):
    response = await client.head('/health/ready')

    assert response.status_code == status.HTTP_200_OK
    assert response.content == b''


async def test_ready_answers_head_with_503_when_the_database_is_unreachable():
    app = create_app(make_test_settings(database_url=UNREACHABLE_DATABASE_URL))

    async with make_client(app) as client:
        response = await client.head('/health/ready')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.content == b''


async def test_an_unavailable_probe_is_a_warning_not_an_error(caplog: pytest.LogCaptureFixture):
    app = create_app(make_test_settings(database_url=UNREACHABLE_DATABASE_URL))

    with caplog.at_level(logging.DEBUG, logger='app.observability.middleware'):
        async with make_client(app) as client:
            await client.get('/health/ready')

    (line,) = [line for line in rendered(caplog.records, 'app.observability.middleware') if 'status_code' in line]
    # 503 은 이 주소의 답이다. 서버의 잘못(error)이 아니다. 결과 칸은 다른 5xx 처럼 server_error 다
    assert (line['level'], line['status_code'], line['result']) == ('warning', 503, 'server_error')
