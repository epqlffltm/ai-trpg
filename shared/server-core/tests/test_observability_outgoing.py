# shared/server-core/tests/test_observability_outgoing.py

"""
인증 서버를 부를 때 추적(traceparent)을 이어 주는지 검증한다(server_core/observability/context.py 의 outgoing_headers).
요청의 식별자(X-Request-ID)는 넘기지 않는다. 받는 서버가 제 것을 만든다. 규격은 docs/observability.md 에 있다.
"""

import httpx
import pytest

from server_core.auth.jwks import fetch_jwks
from server_core.auth.revocations import fetch_revocations
from server_core.observability.context import request_scope
from server_core.observability.identifiers import new_trace, parse_traceparent
from server_core.testing.tokens import FakeAuthServer

JWKS_URL = 'http://auth.test/api/v1/auth/jwks'
REVOCATIONS_URL = 'http://auth.test/api/v1/auth/session-revocations'

FETCHES = [
    pytest.param(fetch_jwks, JWKS_URL, id='jwks'),
    pytest.param(fetch_revocations, REVOCATIONS_URL, id='revocations'),
]


def recording_client(auth_server: FakeAuthServer, received: list[httpx.Request]) -> httpx.AsyncClient:
    """가짜 인증 서버로 가는 클라이언트. 보낸 요청을 received 에 담는다."""

    async def record(request: httpx.Request) -> None:
        received.append(request)

    client = auth_server.make_client()
    client.event_hooks['request'].append(record)
    return client


@pytest.mark.parametrize(('fetch', 'url'), FETCHES)
async def test_calling_the_auth_server_carries_the_trace_on(auth_server: FakeAuthServer, fetch, url: str):
    received: list[httpx.Request] = []
    trace = new_trace()

    async with recording_client(auth_server, received) as client:
        with request_scope('request-12345', trace):
            await fetch(client, url)

    (request,) = received
    assert parse_traceparent(request.headers['traceparent']) == trace
    assert 'x-request-id' not in request.headers


@pytest.mark.parametrize(('fetch', 'url'), FETCHES)
async def test_calling_the_auth_server_outside_a_request_sends_no_trace(auth_server: FakeAuthServer, fetch, url: str):
    # 끊긴 세션의 목록은 요청 밖(뒤에서 도는 작업)에서 받는다. 이을 추적이 없다
    received: list[httpx.Request] = []

    async with recording_client(auth_server, received) as client:
        await fetch(client, url)

    assert 'traceparent' not in received[0].headers
