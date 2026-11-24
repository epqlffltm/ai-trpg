# shared/server-core/src/server_core/auth/responses.py

"""
토큰을 확인하지 못했을 때(503)의 본문에 까닭의 이름(code)을 싣는 처리기.
서버는 앱을 만들 때 use_auth_errors(app) 를 부른다.

인증 서버가 꺼져 공개키를 구할 수 없으면 서버들은 토큰을 확인하지 못해 503 을 낸다(dependencies.py).
화면은 503 이면 "결제 서버가 지금 답하지 못합니다"처럼 부른 서버의 탓으로 적었다. 까닭은 그 서버가 아니라 인증이다.
본문에 code(auth_unavailable)를 실어 화면이 "로그인을 확인할 수 없습니다"로 가른다. 결제 서버(Go)도 같은 이름을 싣는다.

처리기를 걸지 않은 앱도 깨지지 않는다. 오류가 HTTPException 이라 FastAPI 의 기본 처리기가 code 없이 같은 503 을 낸다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server_core.auth.dependencies import AUTH_UNAVAILABLE_CODE, VerificationUnavailable
from server_core.error_handlers import add_error_handler


async def handle_verification_unavailable(request: Request, error: VerificationUnavailable) -> JSONResponse:
    """토큰을 확인하지 못했다. 503 에 글과 code, 기다릴 초(Retry-After)를 싣는다."""
    return JSONResponse(
        status_code=error.status_code,
        content={'detail': error.detail, 'code': AUTH_UNAVAILABLE_CODE},
        headers=error.headers,
    )


def use_auth_errors(app: FastAPI) -> None:
    """토큰을 확인하지 못한 503 에 code 를 싣는 처리기를 앱에 건다."""
    add_error_handler(app, VerificationUnavailable, handle_verification_unavailable)
