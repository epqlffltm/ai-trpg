# board-server/contract/tests/test_health.py

"""
살아 있는지(/health), 준비됐는지(/health/ready) 확인하는 주소(board-server/test/health.e2e-spec.ts).
프록시와 관리 도구가 부르는 주소라 버전이 붙은 API 주소 밖에 있다.
"""

import httpx

from tests.urls import API, HEALTH, READY


def test_health_returns_ok_without_login(client: httpx.Client):
    response = client.get(HEALTH)

    assert response.status_code == httpx.codes.OK
    assert response.json() == {'status': 'ok'}


def test_health_is_outside_api_prefix(client: httpx.Client):
    response = client.get(f'{API}/health')

    assert response.status_code == httpx.codes.NOT_FOUND


def test_server_framework_is_not_advertised(client: httpx.Client):
    response = client.get(HEALTH)

    assert 'x-powered-by' not in response.headers


def test_ready_returns_ok_when_database_is_reachable(client: httpx.Client):
    response = client.get(READY)

    assert response.status_code == httpx.codes.OK
    assert response.json() == {'status': 'ok'}


def test_ready_is_outside_api_prefix(client: httpx.Client):
    response = client.get(f'{API}/health/ready')

    assert response.status_code == httpx.codes.NOT_FOUND
