# notification-server/app/core/signed_requests.py

"""
다른 서버가 서명해 보낸 요청을 읽고 확인하는 도구(server_core/service_auth/signing.py).

알림을 넣는 주소(app/notifications/router.py)와 탈퇴를 받는 주소(app/withdrawals/router.py)가 함께 쓴다.
  - 본문은 서명을 확인한 뒤에 해석한다. 서명을 확인하려면 본문 전체가 있어야 해서, 그 전에 크기부터 자른다
  - 서명을 받아들일 수 없으면 이유를 싣지 않은 401 이다. 무엇이 틀렸는지 알려 주면 꾸며 내는 쪽에 도움이 된다
"""

import time

from fastapi import HTTPException, Request, status
from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid

# 받는 본문의 상한(바이트). 알림 하나에는 이만큼이면 넉넉하다(값은 2048바이트까지)
BODY_MAX_BYTES = 16 * 1024


def unauthorized() -> HTTPException:
    """서명을 받아들일 수 없을 때의 응답. 이유를 싣지 않는다."""
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='요청의 서명이 맞지 않습니다.')


def signed_path(request: Request) -> str:
    """서명하는 주소. 호스트를 뺀 경로와, 있으면 쿼리다."""
    query = request.url.query
    return f'{request.url.path}?{query}' if query else request.url.path


async def read_body(request: Request) -> bytes:
    """본문을 읽는다. 상한을 넘으면 413 이다. 서명을 확인하기 전에 큰 본문을 끝까지 읽지 않는다."""
    declared = request.headers.get('content-length')
    if declared is not None and declared.isdigit() and int(declared) > BODY_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail='본문이 너무 큽니다.')
    body = b''
    async for chunk in request.stream():
        body += chunk
        if len(body) > BODY_MAX_BYTES:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail='본문이 너무 큽니다.')
    return body


async def body_signed_with(request: Request, secret: str) -> bytes:
    """
    본문을 읽고 그 비밀로 서명했는지 본다. 맞으면 본문을, 아니면 401 이다.

    비밀이 비어 있으면 어떤 서명도 맞지 않는다(is_valid). 그 서버의 요청은 받지 않는 것이다.
    """
    body = await read_body(request)
    header = request.headers.get(SIGNATURE_HEADER)
    if not is_valid(secret, header, request.method, signed_path(request), body, time.time()):
        raise unauthorized()
    return body
