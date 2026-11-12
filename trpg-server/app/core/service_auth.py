# trpg-server/app/core/service_auth.py

"""
다른 서버가 부르는 주소의 서명을 확인한다. 지금은 인증 서버의 탈퇴 알림(app/withdrawal/) 하나다.

    POST /api/v1/game/service/users/{public_id}/withdrawal
    X-Service-Signature: t=<보낸 시각(초)>,v1=<HMAC-SHA256(비밀, "<시각>.<메서드>\\n<주소>\\n<본문>")>

  - 서명의 모양은 게임 서버가 결제 서버와 알림 서버에 보낼 때와 같다(server_core/service_auth/signing.py)
  - 주소와 본문, 시각까지 서명한다. 앞뒤 5분(TOLERANCE_SECONDS)을 넘긴 서명은 받지 않는다
  - 서명이 없거나, 틀렸거나, 오래됐거나, 비밀이 설정에 없으면(짧으면) 모두 401 이다. 어느 경우인지 나누지 않는다
  - 본문은 서명을 확인한 뒤에 해석한다. 서명을 확인하기 전에 크기부터 자른다(413)

본문을 읽고(크기를 자르고) 서명을 확인하는 것은 공용 코드다(server_core/service_auth/receiving.py, #1266).
여기는 인증 서버의 비밀로 확인하는 FastAPI 의 의존성만 둔다.
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
