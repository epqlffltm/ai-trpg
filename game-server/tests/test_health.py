# game-server/tests/test_health.py

"""
서버 프로세스가 살아 있는지 확인하는 API 를 검증한다.
"""

from fastapi import status
from httpx import AsyncClient

from app.main import create_app
from tests.conftest import make_client, make_test_settings

# 아무도 듣고 있지 않은 포트. 연결이 바로 거부된다
UNREACHABLE_DATABASE_URL = 'postgresql+asyncpg://game:wrong@127.0.0.1:1/trpg'


async def test_health_returns_ok(client: AsyncClient):
    response = await client.get('/health')

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok'}


async def test_health_needs_no_login(client: AsyncClient):
    # 프록시와 관리 도구가 부른다. 토큰을 줄 수 없다
    response = await client.get('/health')

    assert response.status_code != status.HTTP_401_UNAUTHORIZED


async def test_health_does_not_depend_on_the_database():
    app = create_app(make_test_settings(database_url=UNREACHABLE_DATABASE_URL))

    async with make_client(app) as client:
        response = await client.get('/health')

    # DB 가 죽었다고 관리 도구가 서버까지 재시작하면 안 된다
    assert response.status_code == status.HTTP_200_OK
