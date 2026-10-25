# board-server/app/core/service_auth.py

"""
인증 서버가 서명한 요청만 들여보낸다. 탈퇴를 받는 주소(app/withdrawal/)에 의존성으로 건다.

    X-Service-Signature: t=<보낸 시각(초)>,v1=<HMAC-SHA256(비밀, "<시각>.<메서드>\\n<경로>\\n<본문>") 의 16진수>

  - 사용자의 토큰이 아니라 요청의 서명을 본다. 비밀은 AUTH_SERVER_SECRET(인증 서버의 BOARD_SECRET)이다
  - 서명은 받은 바이트 그대로에 한다. 경로는 앞부분(/api/v1/board)과 쿼리를 포함한 그대로다.
    보내는 쪽(auth-server/accounts/withdrawal_client.py)이 그렇게 서명한다
  - 비밀이 비었거나 짧거나, 서명이 없거나, 틀렸거나, 5분을 넘겼으면 401 이다. 이유를 나누지 않는다
  - 본문의 검사보다 먼저 돈다. 서명을 확인하기 전에는 본문의 모양을 알려 주지 않는다.
    다만 본문이 JSON 이 아니면 서명보다 먼저 400 이다(본문을 읽는 단계다. NestJS 로 쓰던 때도 같았다)

서명의 모양과 셈은 공용 코드(server_core/service_auth/signing.py)의 것을 쓴다.
머리말을 읽는 법만 NestJS 로 쓰던 때(src/service-auth/signing.ts)와 같게 따로 둔다.
그때는 시각을 수로 바꾼 뒤 그 수로 서명을 셈했다(t=0042 는 "42" 로 셈한다). 지금의 보내는 쪽과는 어느 쪽이든 같다.
"""

import hmac
import math
import re
import time

from fastapi import Request, status
from server_core.service_auth.signing import MIN_SECRET_LENGTH, SIGNATURE_HEADER, TOLERANCE_SECONDS, digest

from app.core.errors import ApiError

# 서명이 맞지 않을 때의 응답. 무엇이 틀렸는지 싣지 않는다
BAD_SIGNATURE_DETAIL = '요청의 서명이 맞지 않습니다.'

# 머리말의 모양. 시각은 정수, 서명은 16진수 64자다
HEADER = re.compile(r'^t=(?P<sent_at>-?\d{1,19}),v1=(?P<signature>[0-9a-f]{64})\Z', re.ASCII)

# API 목록에 적는 서명의 머리말. 의존성이 머리말을 직접 읽으므로(없으면 400 이 아니라 401) 따로 적는다
SIGNATURE_PARAMETER = {
    'name': SIGNATURE_HEADER,
    'in': 'header',
    'required': True,
    'description': '인증 서버의 서명(t=<초>,v1=<HMAC>). 비밀은 AUTH_SERVER_SECRET 이다. 틀리면 401',
    'schema': {'type': 'string'},
}


def now_seconds() -> int:
    """지금 시각(초). 소수점 아래는 버린다."""
    return math.floor(time.time())


def is_valid_signature(secret: str, header: str | None, method: str, path: str, body: bytes, now: int) -> bool:
    """
    머리말의 서명이 이 요청(메서드, 경로, 본문)의 것이고 방금 만든 것인가.

    이유를 나누지 않고 참/거짓만 답한다. 비밀이 비었거나 짧으면 하나도 받지 않는다.
    """
    if len(secret) < MIN_SECRET_LENGTH or header is None:
        return False
    parts = HEADER.match(header)
    if parts is None:
        return False
    sent_at = int(parts['sent_at'])
    expected = digest(secret, str(sent_at), method, path, body)
    # 두 서명을 견줄 때 걸리는 시간이 어디서 틀렸는지에 따라 달라지지 않게 한다
    if not hmac.compare_digest(parts['signature'].encode(), expected.encode()):
        return False
    return abs(now - sent_at) <= TOLERANCE_SECONDS


def signed_path(request: Request) -> str:
    """서명하는 경로. 받은 그대로의 경로(퍼센트 인코딩을 풀지 않는다)와, 있으면 쿼리다."""
    raw_path: bytes = request.scope.get('raw_path') or request.url.path.encode()
    path = raw_path.decode('latin-1').split('?', 1)[0]
    query = request.url.query
    return f'{path}?{query}' if query else path


def auth_server_secret(request: Request) -> str:
    """인증 서버의 서명 비밀. 비어 있으면 빈 글이다(is_valid_signature 가 받지 않는다)."""
    return request.app.state.settings.auth_server_secret.get_secret_value()


async def verify_auth_server(request: Request) -> None:
    """인증 서버가 서명한 요청인지 확인한다. 아니면 401 이다. FastAPI 의 의존성으로 쓴다."""
    body = await request.body()
    header = request.headers.get(SIGNATURE_HEADER)
    secret = auth_server_secret(request)
    if not is_valid_signature(secret, header, request.method, signed_path(request), body, now_seconds()):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, BAD_SIGNATURE_DETAIL)
