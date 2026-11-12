# chat-server/app/core/service_auth.py

"""
다른 서버가 부르는 주소의 서명을 확인한다. 본문을 읽고 서명을 확인하는 것은 공용 코드다
(server_core/service_auth/receiving.py, #1266). 여기는 어느 비밀을 받는지와 FastAPI 의 의존성이다.

    /api/v1/chat/service/users/{public_id}/withdrawal   인증 서버의 탈퇴 알림(app/withdrawal/, #670)
    /api/v1/chat/service/stats/character-starts         asset 서버가 받아 가는 대화 수(app/stats/, #985)

  - 서명이 없거나 틀렸거나 오래됐거나, 인증 서버의 비밀이 설정에 없으면 401 이다. 어느 경우인지 나누지 않는다
  - 본문은 서명을 확인한 뒤에 쓴다. 받은 바이트 그대로 서명을 본다
  - 탈퇴 알림에는 사용자의 토큰이 없다(탈퇴한 사람은 토큰이 없다). 인증 서버의 비밀이 그 길만 연다
  - asset 서버는 이 서버가 asset 서버를 부를 때 쓰는 비밀(ASSET_SECRET)로 서명한다. 한 짝에 비밀 하나다
"""

from typing import Annotated

from fastapi import Depends, Request
from server_core.service_auth.receiving import verified_body


def auth_server_secret(request: Request) -> str:
    """인증 서버의 서명 비밀. 비어 있으면 빈 글이다(is_valid 가 받지 않는다)."""
    return request.app.state.settings.auth_server_secret.get_secret_value()


async def verify_auth_server(request: Request) -> bytes:
    """인증 서버의 서명을 확인하고 본문을 돌려준다. FastAPI 의 의존성으로 쓴다. 본문은 그다음에 해석한다."""
    return await verified_body(request, auth_server_secret(request))


# 인증 서버가 서명한 본문
AuthServerBody = Annotated[bytes, Depends(verify_auth_server)]


def asset_server_secret(request: Request) -> str:
    """asset 서버의 서명 비밀. 이 서버가 asset 서버를 부를 때 쓰는 것(ASSET_SECRET)과 같다. 비어 있으면 빈 글이다."""
    return request.app.state.settings.asset_secret.get_secret_value()


async def verify_asset_server(request: Request) -> bytes:
    """asset 서버의 서명을 확인하고 본문을 돌려준다(GET 이라 비어 있다). FastAPI 의 의존성으로 쓴다."""
    return await verified_body(request, asset_server_secret(request))


# asset 서버가 서명한 요청(#985). 서명은 주소까지 덮어 이 서버가 asset 서버에 보낸 서명을 되돌려 쓸 수 없다
AssetServerBody = Annotated[bytes, Depends(verify_asset_server)]
