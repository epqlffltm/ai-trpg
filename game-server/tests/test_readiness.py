# game-server/tests/test_readiness.py

"""
서버가 요청을 처리할 준비가 됐는지 확인하는 API 를 검증한다.

Redis 를 보는 테스트는 실제 Redis 에서 돈다(tests/test_attempt_limits.py 와 같은 TEST_REDIS_URL).
"""

import asyncio
import logging
import time

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.api import readiness
from app.main import create_app
from tests.conftest import make_client, make_test_settings
from tests.logs import rendered
from tests.test_attempt_limits import REDIS_URL
from tests.test_health import UNREACHABLE_DATABASE_URL

# 아무도 듣고 있지 않은 포트. 연결이 바로 거부된다
UNREACHABLE_REDIS_URL = 'redis://127.0.0.1:1/0'


class HangingRedis:
    """PING 에 답하지 않는 Redis. 연결된 채 멈춘 상황이다."""

    async def ping(self) -> bool:
        await asyncio.sleep(30)
        return True


async def ready_with(caplog: pytest.LogCaptureFixture, **overrides):
    """설정을 바꾼 앱에 준비 확인을 한 번 보낸다. 응답과, 그 확인이 남긴 경고를 돌려준다."""
    app = create_app(make_test_settings(**overrides))
    try:
        with caplog.at_level(logging.WARNING, logger='app.api.readiness'):
            async with make_client(app) as client:
                response = await client.get('/health/ready')
    finally:
        if app.state.redis is not None:
            await app.state.redis.aclose()
    return response, [record.getMessage() for record in caplog.records if record.name == 'app.api.readiness']


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


async def test_ready_logs_only_the_kind_of_database_error(caplog: pytest.LogCaptureFixture):
    response, warnings = await ready_with(caplog, database_url=UNREACHABLE_DATABASE_URL)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    (warning,) = warnings
    assert warning.startswith('준비되지 않았다: DB 에 닿지 않는다(')
    # 오류의 글에는 DB 주소와 계정 이름이 들어 있다. 종류만 남긴다
    assert '127.0.0.1' not in warning


async def test_ready_is_ok_when_the_redis_in_use_answers(caplog: pytest.LogCaptureFixture):
    response, warnings = await ready_with(caplog, redis_url=REDIS_URL)

    assert response.status_code == status.HTTP_200_OK
    assert warnings == []


async def test_ready_returns_503_when_the_redis_in_use_is_unreachable(caplog: pytest.LogCaptureFixture):
    # #258: Redis 를 쓰면 로비 비밀번호와 채팅의 시도 제한이 닫힌 쪽으로 실패한다. 요청을 처리할 수 없는 서버다
    response, warnings = await ready_with(caplog, redis_url=UNREACHABLE_REDIS_URL)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {'status': 'unavailable'}
    (warning,) = warnings
    assert warning.startswith('준비되지 않았다: Redis 에 닿지 않는다(')
    assert '127.0.0.1' not in warning


async def test_ready_does_not_look_at_redis_when_it_is_not_used(app: FastAPI, client: AsyncClient):
    # REDIS_URL 이 없으면 서버 안의 메모리로 센다. Redis 가 없어도 준비된 것이다
    assert app.state.redis is None

    response = await client.get('/health/ready')

    assert response.status_code == status.HTTP_200_OK


async def test_ready_gives_up_when_a_dependency_hangs(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    # 연결된 채 멈춘 것 앞에서도 확인 요청은 정한 시간에 503 으로 끝난다
    monkeypatch.setattr(readiness, 'READINESS_TIMEOUT_SECONDS', 0.2)
    app = create_app(make_test_settings())
    app.state.redis = HangingRedis()

    with caplog.at_level(logging.WARNING, logger='app.api.readiness'):
        async with make_client(app) as client:
            started = time.monotonic()
            response = await client.get('/health/ready')
            elapsed = time.monotonic() - started

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert elapsed < 5
    assert '준비되지 않았다: 0.2초 안에 확인이 끝나지 않았다' in caplog.messages
