# game-server/tests/test_readiness.py

"""
서버가 요청을 처리할 준비가 됐는지 확인하는 API 를 검증한다.
"""

from fastapi import status
from httpx import AsyncClient

from app.main import create_app
from tests.conftest import make_client, make_test_settings
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
