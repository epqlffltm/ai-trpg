# game-server/tests/test_health.py

"""
서버가 살아 있는지 확인하는 API 를 검증한다.
"""

from fastapi import status
from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient):
    response = await client.get('/health')

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok'}


async def test_health_needs_no_login(client: AsyncClient):
    # 프록시와 관리 도구가 부른다. 토큰을 줄 수 없다
    response = await client.get('/health')

    assert response.status_code != status.HTTP_401_UNAUTHORIZED
