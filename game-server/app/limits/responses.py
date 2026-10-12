# game-server/app/limits/responses.py

"""
막혔을 때의 HTTP 응답. 처리기는 app/main.py 에 등록한다.

인증 서버와 같은 모양이다(auth-server/accounts/exception_handlers.py). 화면이 서버를 가리지 않고 같은 것을 읽는다.
무엇을 기준으로 셌는지(사람, 테이블), 몇 번까지인지는 알려 주지 않는다. 기다릴 초만 본문과 Retry-After 에 싣는다.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.limits.attempts import LimitsUnavailable, TooManyAttempts


async def handle_too_many_attempts(request: Request, error: TooManyAttempts) -> JSONResponse:
    """허용된 횟수를 넘었다. 429."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            'detail': '시도가 너무 많습니다. 잠시 뒤에 다시 시도해 주세요.',
            'code': 'too_many_attempts',
            'retry_after': error.retry_after,
        },
        headers={'Retry-After': str(error.retry_after)},
    )


async def handle_limits_unavailable(request: Request, error: LimitsUnavailable) -> JSONResponse:
    """세는 곳에 닿지 못해 막았다. 503. 잠시 뒤에 다시 하면 된다."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={'detail': '지금은 확인할 수 없습니다. 잠시 뒤에 다시 시도해 주세요.', 'code': 'limits_unavailable'},
    )
