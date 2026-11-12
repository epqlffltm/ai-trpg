# asset-server/app/core/service_auth.py

"""
다른 서버가 부르는 주소의 서명을 확인한다. 본문을 읽고 서명을 확인하는 것은 공용 코드다
(server_core/service_auth/receiving.py, #1266). 여기는 어느 비밀을 받는지와 FastAPI 의 의존성이다.

    /api/v1/asset/service/{caller}/...                   페르소나와 판을 가져가는 서버(chat, story, 나중에 TRPG)
    /api/v1/asset/service/{caller}/images                만든 장면 그림을 맡기는 서버(chat, story, #983)
    /api/v1/asset/service/users/{public_id}/withdrawal   인증 서버의 탈퇴 알림(app/withdrawal/)

  - caller 는 부르는 서버의 이름이다. 주소까지 서명하므로 남의 이름으로 부를 수 없다
  - 서명이 없거나 틀렸거나 오래됐거나, 그 서버의 비밀이 설정에 없으면 401 이다. 어느 경우인지 나누지 않는다
  - 본문은 서명을 확인한 뒤에 쓴다. 받은 바이트 그대로 서명을 본다(가져가는 길은 GET 이라 본문이 비어 있다)
  - 서명은 "어느 서버가 부르나"만 증명한다. 가져가는 길에서 "누구를 위해 가져가나"는
    함께 넘긴 사용자의 토큰(CurrentUser)이 증명한다.
    그래서 서버의 비밀이 새도 그 비밀만으로는 아무의 페르소나도 가져가지 못한다(토큰이 있어야 한다).
    탈퇴 알림에는 토큰이 없다(탈퇴한 사람은 토큰이 없다). 인증 서버의 비밀이 그 길만 연다
"""

from typing import Annotated

from fastapi import Depends, Path, Request
from server_core.service_auth.receiving import verified_body

# 부르는 서버의 이름의 모양. 설정에 없는 이름은 비밀이 없는 것과 같다(401)
CALLER_PATTERN = r'^[a-z][a-z0-9_-]{0,31}$'


def caller_secret(request: Request, caller: str) -> str:
    """그 서버의 서명 비밀. 모르는 서버이거나 비어 있으면 빈 글이다(is_valid 가 받지 않는다)."""
    return request.app.state.settings.service_secrets().get(caller, '')


def auth_server_secret(request: Request) -> str:
    """인증 서버의 서명 비밀. 비어 있으면 빈 글이다(is_valid 가 받지 않는다)."""
    return request.app.state.settings.auth_server_secret.get_secret_value()


async def verify_caller(request: Request, caller: Annotated[str, Path(pattern=CALLER_PATTERN)]) -> str:
    """
    부르는 서버의 서명을 확인하고 그 이름을 돌려준다. FastAPI 의 의존성으로 쓴다.

    모르는 서버이거나 그 서버의 비밀이 비어 있으면 401 이다. 404 로 나누지 않는다(어느 이름이 있는지 알리지 않는다).
    """
    await verified_body(request, caller_secret(request, caller))
    return caller


async def verified_image_body(request: Request, caller: Annotated[str, Path(pattern=CALLER_PATTERN)]) -> bytes:
    """
    그림을 맡기는 서버의 서명을 확인하고 그림의 바이트(본문)를 돌려준다. FastAPI 의 의존성으로 쓴다.
    본문의 상한은 그림 올리기와 같다(설정의 image_max_bytes).
    """
    limit = request.app.state.settings.image_max_bytes
    return await verified_body(request, caller_secret(request, caller), limit)


async def verify_auth_server(request: Request) -> bytes:
    """인증 서버의 서명을 확인하고 본문을 돌려준다. FastAPI 의 의존성으로 쓴다. 본문은 그다음에 해석한다."""
    return await verified_body(request, auth_server_secret(request))


# 서명을 확인한 부르는 서버의 이름. 라우터의 의존성(dependencies=[...])이나 인자로 쓴다
SignedCaller = Annotated[str, Depends(verify_caller)]
# 그림을 맡기는 서버가 서명한 그림의 바이트
SignedImageBody = Annotated[bytes, Depends(verified_image_body)]
# 인증 서버가 서명한 본문
AuthServerBody = Annotated[bytes, Depends(verify_auth_server)]
