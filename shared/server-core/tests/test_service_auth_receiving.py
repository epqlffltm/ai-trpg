# shared/server-core/tests/test_service_auth_receiving.py

"""
서명해 보낸 요청을 받는 쪽(server_core/service_auth/receiving.py)을 검증한다(#1266).

보는 것.
  - 맞는 서명이면 받은 바이트 그대로 돌려준다. 쿼리까지 서명한다
  - 서명이 없거나, 다른 비밀이거나, 본문이나 주소를 바꿨거나, 오래됐거나, 비밀이 비었으면 모두 같은 401 이다
  - 본문이 상한을 넘으면 서명을 보기 전에 413 이다. 머리말이 크다고 하면 읽지 않고, 흘려 보내도 넘으면 413 이다
  - 상한은 부르는 쪽이 넘길 수 있다(그림)
서버마다 어느 비밀을 받는지는 쓰는 서버의 테스트(asset, chat, story, 게임, 알림)가 본다.
"""

import time
from collections.abc import AsyncIterator
from typing import cast

import pytest
from fastapi import FastAPI, HTTPException, Request, status
from httpx import ASGITransport, AsyncClient

from server_core.service_auth.receiving import BODY_MAX_BYTES, read_body, signed_path, verified_body
from server_core.service_auth.signing import SIGNATURE_HEADER, TOLERANCE_SECONDS, sign

SECRET = 'a-test-secret-that-is-long-enough-32'
OTHER = 'another-test-secret-long-enough-32b'
SMALL_LIMIT = 8


def receiving_app(secret: str = SECRET) -> FastAPI:
    """서명한 본문을 받는 주소와, 작은 상한으로 받는 주소를 가진 앱."""
    app = FastAPI()

    @app.post('/signed', status_code=status.HTTP_200_OK)
    async def signed(request: Request) -> dict:
        body = await verified_body(request, secret)
        return {'body': body.decode(), 'path': signed_path(request)}

    @app.post('/small', status_code=status.HTTP_200_OK)
    async def small(request: Request) -> dict:
        return {'size': len(await verified_body(request, secret, SMALL_LIMIT))}

    @app.post('/read', status_code=status.HTTP_200_OK)
    async def read(request: Request) -> dict:
        return {'size': len(await read_body(request, SMALL_LIMIT))}

    return app


def signature(path: str, body: bytes, secret: str = SECRET, at: float | None = None) -> dict[str, str]:
    """그 주소와 본문에 대한 서명의 머리말."""
    sent_at = int(time.time() if at is None else at)
    return {SIGNATURE_HEADER: sign(secret, sent_at, 'POST', path, body)}


async def post(app: FastAPI, path: str, body: bytes, headers: dict[str, str]):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        return await client.post(path, content=body, headers=headers)


async def test_a_right_signature_gives_the_body_as_sent():
    body = b'{"at": "2026-11-12T00:00:00Z"}'

    response = await post(receiving_app(), '/signed', body, signature('/signed', body))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'body': body.decode(), 'path': '/signed'}


async def test_the_query_is_signed_too():
    body = b'{}'

    right = await post(receiving_app(), '/signed?since=1', body, signature('/signed?since=1', body))
    without_query = await post(receiving_app(), '/signed?since=1', body, signature('/signed', body))

    assert (right.status_code, right.json()['path']) == (status.HTTP_200_OK, '/signed?since=1')
    assert without_query.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.parametrize(
    'headers',
    [
        {},
        signature('/signed', b'{}', secret=OTHER),
        signature('/signed', b'{"changed": true}'),
        signature('/other', b'{}'),
        signature('/signed', b'{}', at=time.time() - TOLERANCE_SECONDS - 60),
        {SIGNATURE_HEADER: 't=1,v1=00'},
    ],
    ids=['none', 'other secret', 'other body', 'other path', 'stale', 'garbage'],
)
async def test_signatures_it_cannot_accept_are_one_401(headers: dict[str, str]):
    response = await post(receiving_app(), '/signed', b'{}', headers)

    # 무엇이 틀렸는지 나누지 않는다
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {'detail': '요청의 서명이 맞지 않습니다.'}


async def test_an_empty_secret_accepts_nothing():
    response = await post(receiving_app(secret=''), '/signed', b'{}', signature('/signed', b'{}', secret=''))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_a_body_over_the_limit_is_413_before_the_signature():
    body = b'x' * (SMALL_LIMIT + 1)

    response = await post(receiving_app(), '/small', body, {})

    # 서명이 없어도 크기부터 자른다. 서명을 보려고 큰 본문을 끝까지 읽지 않는다
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert response.json() == {'detail': '본문이 너무 큽니다.'}


async def test_the_default_limit_is_the_shared_one():
    body = b'x' * (BODY_MAX_BYTES + 1)

    response = await post(receiving_app(), '/signed', body, signature('/signed', body))

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


async def test_a_streamed_body_over_the_limit_is_413_too():
    async def chunks() -> AsyncIterator[bytes]:
        # 길이를 알리지 않고 흘려 보낸다(Content-Length 가 없다)
        for _ in range(3):
            yield b'xxxx'

    async with AsyncClient(transport=ASGITransport(app=receiving_app()), base_url='http://test') as client:
        response = await client.post('/read', content=chunks())

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


async def test_a_body_within_the_limit_is_read_whole():
    async with AsyncClient(transport=ASGITransport(app=receiving_app()), base_url='http://test') as client:
        response = await client.post('/read', content=b'x' * SMALL_LIMIT)

    assert response.json() == {'size': SMALL_LIMIT}


class DeclaringRequest:
    """머리말만 가진 요청. 본문을 읽으려 하면 실패한다(읽지 않는지 본다)."""

    def __init__(self, length: str) -> None:
        self.headers = {'content-length': length}

    async def stream(self) -> AsyncIterator[bytes]:
        raise AssertionError('본문을 읽었다')
        yield b''


async def test_a_declared_length_over_the_limit_is_refused_without_reading():
    with pytest.raises(HTTPException) as refused:
        await read_body(cast(Request, DeclaringRequest(str(SMALL_LIMIT + 1))), SMALL_LIMIT)

    assert refused.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
