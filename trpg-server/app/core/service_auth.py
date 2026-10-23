# trpg-server/app/core/service_auth.py

"""
다른 서버가 부르는 주소의 서명을 확인한다. 지금은 인증 서버의 탈퇴 알림(app/withdrawal/) 하나다.

    POST /api/v1/game/service/users/{public_id}/withdrawal
    X-Service-Signature: t=<보낸 시각(초)>,v1=<HMAC-SHA256(비밀, "<시각>.<메서드>\\n<주소>\\n<본문>")>

  - 서명의 모양은 게임 서버가 결제 서버와 알림 서버에 보낼 때와 같다(server_core/service_auth/signing.py)
  - 주소와 본문, 시각까지 서명한다. 앞뒤 5분(TOLERANCE_SECONDS)을 넘긴 서명은 받지 않는다
  - 서명이 없거나, 틀렸거나, 오래됐거나, 비밀이 설정에 없으면(짧으면) 모두 401 이다. 어느 경우인지 나누지 않는다
  - 본문은 서명을 확인한 뒤에 해석한다. 서명을 확인하기 전에 크기부터 자른다(413)

서명을 확인하는 것(is_valid)과 시각의 허용 범위는 공용 코드의 것이다(server_core/service_auth/signing.py, #589).
여기는 FastAPI 의 의존성으로 본문을 읽고(크기를 자르고) 인증 서버의 비밀로 확인하는 것만 한다.
"""

import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid

# 받는 본문의 상한(바이트). 탈퇴 알림은 시각 하나라 이만큼이면 넉넉하다
BODY_MAX_BYTES = 16 * 1024


def unauthorized() -> HTTPException:
    """서명을 받아들일 수 없을 때의 응답. 이유를 싣지 않는다. 무엇이 틀렸는지 알려 주면 꾸며 내는 쪽에 도움이 된다."""
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='요청의 서명이 맞지 않습니다.')


def too_large() -> HTTPException:
    """본문이 상한을 넘을 때의 응답."""
    return HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail='본문이 너무 큽니다.')


def signed_path(request: Request) -> str:
    """서명하는 주소. 호스트를 뺀 경로와, 있으면 쿼리다."""
    query = request.url.query
    return f'{request.url.path}?{query}' if query else request.url.path


def declared_too_large(request: Request) -> bool:
    """머리말(Content-Length)이 상한을 넘는다고 말하는가. 그러면 읽기 전에 거절한다."""
    declared = request.headers.get('content-length')
    return declared is not None and declared.isdigit() and int(declared) > BODY_MAX_BYTES


async def read_body(request: Request) -> bytes:
    """본문을 읽는다. 상한을 넘으면 413 이다. 서명을 확인하기 전에 큰 본문을 끝까지 읽지 않는다."""
    if declared_too_large(request):
        raise too_large()
    body = b''
    async for chunk in request.stream():
        body += chunk
        if len(body) > BODY_MAX_BYTES:
            raise too_large()
    return body


async def verify_auth_server(request: Request) -> bytes:
    """인증 서버의 서명을 확인하고 본문을 돌려준다. FastAPI 의 의존성으로 쓴다. 본문은 그다음에 해석한다."""
    body = await read_body(request)
    secret = request.app.state.settings.auth_server_secret.get_secret_value()
    header = request.headers.get(SIGNATURE_HEADER)
    if not is_valid(secret, header, request.method, signed_path(request), body, time.time()):
        raise unauthorized()
    return body


# 인증 서버가 서명한 본문
AuthServerBody = Annotated[bytes, Depends(verify_auth_server)]
