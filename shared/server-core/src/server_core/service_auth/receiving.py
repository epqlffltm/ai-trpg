# shared/server-core/src/server_core/service_auth/receiving.py

"""
우리 서버가 서명해 보낸 요청을 받는 쪽의 도구(#1266). 서명의 셈은 signing.py 다.

asset, chat, story, 게임, 알림 서버가 함께 쓴다. 서버는 이것으로 FastAPI 의 의존성을 만들고,
어느 비밀을 받을지(인증 서버, asset 서버, 주소의 부르는 서버)만 정한다(서버의 app/core/service_auth.py).
  - 본문은 서명을 확인한 뒤에 해석한다. 받은 바이트 그대로 서명을 본다
  - 서명을 확인하려면 본문 전체가 있어야 해서, 그 전에 크기부터 자른다(413). 머리말이 크다고 하면 읽지도 않는다
  - 서명이 없거나, 틀렸거나, 오래됐거나, 비밀이 비었거나 짧으면 모두 401 이다. 어느 경우인지 나누지 않는다.
    무엇이 틀렸는지 알려 주면 꾸며 내는 쪽에 도움이 된다
게시판 서버는 쓰지 않는다. 오류의 모양(ApiError)과, 본문이 JSON 이 아니면 서명보다 먼저 400 인 차례가 다르다.
"""

import time

from fastapi import HTTPException, Request, status

from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid

# 받는 본문의 기본 상한(바이트). 탈퇴 알림, 알림 하나, 가져가는 길(GET)에는 넉넉하다. 그림처럼 큰 것은 상한을 넘긴다
BODY_MAX_BYTES = 16 * 1024


def unauthorized() -> HTTPException:
    """서명을 받아들일 수 없을 때의 응답. 이유를 싣지 않는다."""
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='요청의 서명이 맞지 않습니다.')


def too_large() -> HTTPException:
    """본문이 상한을 넘을 때의 응답."""
    return HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail='본문이 너무 큽니다.')


def signed_path(request: Request) -> str:
    """서명하는 주소. 호스트를 뺀 경로와, 있으면 쿼리다."""
    query = request.url.query
    return f'{request.url.path}?{query}' if query else request.url.path


def declared_too_large(request: Request, limit: int) -> bool:
    """머리말(Content-Length)이 상한을 넘는다고 말하는가. 그러면 읽기 전에 거절한다."""
    declared = request.headers.get('content-length')
    return declared is not None and declared.isdigit() and int(declared) > limit


async def read_body(request: Request, limit: int = BODY_MAX_BYTES) -> bytes:
    """본문을 읽는다. 상한을 넘으면 413 이다. 서명을 확인하기 전에 큰 본문을 끝까지 읽지 않는다."""
    if declared_too_large(request, limit):
        raise too_large()
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        chunks.append(chunk)
        size += len(chunk)
        if size > limit:
            raise too_large()
    return b''.join(chunks)


async def verified_body(request: Request, secret: str, limit: int = BODY_MAX_BYTES) -> bytes:
    """
    본문을 읽고 그 비밀로 서명했는지 본다. 맞으면 받은 본문을, 틀리면 401, 본문이 limit 을 넘으면 413 이다.

    비밀이 비어 있으면 어떤 서명도 맞지 않는다(is_valid). 그 서버의 요청은 받지 않는 것이다.
    """
    body = await read_body(request, limit)
    header = request.headers.get(SIGNATURE_HEADER)
    if not is_valid(secret, header, request.method, signed_path(request), body, time.time()):
        raise unauthorized()
    return body
