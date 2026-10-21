# trpg-server/app/core/service_auth.py

"""
다른 서버가 부르는 주소의 서명을 확인한다. 지금은 인증 서버의 탈퇴 알림(app/withdrawal/) 하나다.

    POST /api/v1/game/service/users/{public_id}/withdrawal
    X-Service-Signature: t=<보낸 시각(초)>,v1=<HMAC-SHA256(비밀, "<시각>.<메서드>\\n<주소>\\n<본문>")>

  - 서명의 모양은 게임 서버가 결제 서버와 알림 서버에 보낼 때와 같다(app/billing/signing.py)
  - 주소와 본문, 시각까지 서명한다. 앞뒤 5분(TOLERANCE_SECONDS)을 넘긴 서명은 받지 않는다
  - 서명이 없거나, 틀렸거나, 오래됐거나, 비밀이 설정에 없으면(짧으면) 모두 401 이다. 어느 경우인지 나누지 않는다
  - 본문은 서명을 확인한 뒤에 해석한다. 서명을 확인하기 전에 크기부터 자른다(413)

확인하는 코드는 공용 코드(server_core/service_auth/signing.py 의 is_valid)와 같은 것이다. 게임 서버는 아직
공용 코드를 쓰지 않는다. 공용 코드로 옮길 때(#589) 이 파일의 확인하는 부분은 그것으로 바꾼다.
"""

import hashlib
import hmac
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.billing.signing import SIGNATURE_HEADER, signed_content

# 서명의 시각이 지금과 벌어져도 되는 가장 긴 시간(초). 앞뒤로 같다. 서버끼리의 시계 차이를 봐준다
TOLERANCE_SECONDS = 5 * 60

# 서명에 쓰는 비밀의 가장 짧은 길이. 그보다 짧은 비밀로는 하나도 받지 않는다
MIN_SECRET_LENGTH = 32

# 받는 본문의 상한(바이트). 탈퇴 알림은 시각 하나라 이만큼이면 넉넉하다
BODY_MAX_BYTES = 16 * 1024


def split_header(header: str) -> tuple[str, str] | None:
    """'t=<시각>,v1=<서명>' 을 시각과 서명으로 나눈다. 그 모양이 아니면 None 이다."""
    time_part, comma, signature_part = header.partition(',')
    if not comma or not time_part.startswith('t=') or not signature_part.startswith('v1='):
        return None
    return time_part.removeprefix('t='), signature_part.removeprefix('v1=')


def is_fresh(sent_at: str, now: float) -> bool:
    """서명의 시각이 지금에서 앞뒤 TOLERANCE_SECONDS 안쪽인가. 숫자가 아니면 아니다."""
    if not sent_at.isascii() or not sent_at.isdigit():
        return False
    return abs(now - int(sent_at)) <= TOLERANCE_SECONDS


def digest(secret: str, sent_at: str, method: str, path: str, body: bytes) -> str:
    """서명 값(16진수). 보내는 쪽(app/billing/signing.py 의 sign)과 같은 글자에 서명한다."""
    content = signed_content(sent_at, method, path, body)
    return hmac.new(secret.encode(), content, hashlib.sha256).hexdigest()


def is_valid(secret: str, header: str | None, method: str, path: str, body: bytes, now: float) -> bool:
    """
    머리말의 서명이 이 요청(메서드, 주소, 본문)의 것이고 방금 만든 것인가.

    비밀이 비었거나 짧으면 누구나 서명을 만들 수 있다. 그런 비밀로는 하나도 받지 않는다.
    """
    if len(secret) < MIN_SECRET_LENGTH or header is None:
        return False
    parts = split_header(header)
    if parts is None:
        return False
    sent_at, signature = parts
    # 두 서명을 견줄 때 걸리는 시간이 어디서 틀렸는지에 따라 달라지지 않게 한다
    if not hmac.compare_digest(signature.encode(), digest(secret, sent_at, method, path, body).encode()):
        return False
    return is_fresh(sent_at, now)


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
