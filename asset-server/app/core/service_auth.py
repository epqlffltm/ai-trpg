# asset-server/app/core/service_auth.py

"""
다른 서버가 부르는 주소의 서명을 확인한다(server_core/service_auth/signing.py).

    /api/v1/asset/service/{caller}/...                   페르소나와 판을 가져가는 서버(chat, 나중에 story, TRPG)
    /api/v1/asset/service/users/{public_id}/withdrawal   인증 서버의 탈퇴 알림(app/withdrawal/)

  - caller 는 부르는 서버의 이름이다. 주소까지 서명하므로 남의 이름으로 부를 수 없다
  - 서명이 없거나 틀렸거나 오래됐거나, 그 서버의 비밀이 설정에 없으면 401 이다. 어느 경우인지 나누지 않는다
  - 본문은 서명을 확인한 뒤에 쓴다. 받은 바이트 그대로 서명을 본다(가져가는 길은 GET 이라 본문이 비어 있다)
  - 서명은 "어느 서버가 부르나"만 증명한다. 가져가는 길에서 "누구를 위해 가져가나"는
    함께 넘긴 사용자의 토큰(CurrentUser)이 증명한다.
    그래서 서버의 비밀이 새도 그 비밀만으로는 아무의 페르소나도 가져가지 못한다(토큰이 있어야 한다).
    탈퇴 알림에는 토큰이 없다(탈퇴한 사람은 토큰이 없다). 인증 서버의 비밀이 그 길만 연다

알림 서버의 것(notification-server/app/notifications/router.py)과 같은 방법이다. 서버끼리 받는 곳이 둘째라
server_core 로 옮길 때가 됐다. app.* 를 가져오지 않게 두어 파일째 옮길 수 있게 한다(설정은 app.state 에서 읽는다).
"""

import time
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request, status
from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid

# 받는 본문의 상한(바이트). 서명을 확인하려면 본문 전체를 읽어야 하므로, 서명을 확인하기 전에 크기부터 자른다.
# 지금의 주소는 모두 GET 이라 본문이 없다. 넉넉히 둔다
BODY_MAX_BYTES = 16 * 1024

# 부르는 서버의 이름의 모양. 설정에 없는 이름은 비밀이 없는 것과 같다(401)
CALLER_PATTERN = r'^[a-z][a-z0-9_-]{0,31}$'


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


def declared_too_large(request: Request, limit: int) -> bool:
    """머리말(Content-Length)이 상한을 넘는다고 말하는가. 그러면 읽기 전에 거절한다."""
    declared = request.headers.get('content-length')
    return declared is not None and declared.isdigit() and int(declared) > limit


async def read_body(request: Request, limit: int = BODY_MAX_BYTES) -> bytes:
    """
    본문을 읽는다. 상한을 넘으면 413 이다. 서명을 확인하기 전에 큰 본문을 끝까지 읽지 않는다.

    그림 올리기(app/images/router.py)도 자기 상한으로 쓴다.
    """
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


def caller_secret(request: Request, caller: str) -> str:
    """그 서버의 서명 비밀. 모르는 서버이거나 비어 있으면 빈 글이다(is_valid 가 받지 않는다)."""
    return request.app.state.settings.service_secrets().get(caller, '')


def auth_server_secret(request: Request) -> str:
    """인증 서버의 서명 비밀. 비어 있으면 빈 글이다(is_valid 가 받지 않는다)."""
    return request.app.state.settings.auth_server_secret.get_secret_value()


async def verified_body(request: Request, secret: str) -> bytes:
    """그 비밀로 서명을 확인하고 받은 본문을 돌려준다. 틀리면 401 이다."""
    body = await read_body(request)
    header = request.headers.get(SIGNATURE_HEADER)
    if not is_valid(secret, header, request.method, signed_path(request), body, time.time()):
        raise unauthorized()
    return body


async def verify_caller(request: Request, caller: Annotated[str, Path(pattern=CALLER_PATTERN)]) -> str:
    """
    부르는 서버의 서명을 확인하고 그 이름을 돌려준다. FastAPI 의 의존성으로 쓴다.

    모르는 서버이거나 그 서버의 비밀이 비어 있으면 401 이다. 404 로 나누지 않는다(어느 이름이 있는지 알리지 않는다).
    """
    await verified_body(request, caller_secret(request, caller))
    return caller


async def verify_auth_server(request: Request) -> bytes:
    """인증 서버의 서명을 확인하고 본문을 돌려준다. FastAPI 의 의존성으로 쓴다. 본문은 그다음에 해석한다."""
    return await verified_body(request, auth_server_secret(request))


# 서명을 확인한 부르는 서버의 이름. 라우터의 의존성(dependencies=[...])이나 인자로 쓴다
SignedCaller = Annotated[str, Depends(verify_caller)]
# 인증 서버가 서명한 본문
AuthServerBody = Annotated[bytes, Depends(verify_auth_server)]
