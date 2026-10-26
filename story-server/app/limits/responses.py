# story-server/app/limits/responses.py

"""
막혔을 때의 HTTP 응답. 처리기는 app/main.py 에 등록한다.

인증 서버, 게임 서버, chat 서버와 같은 모양이다. 화면이 서버를 가리지 않고 같은 것을 읽는다.
몇 번까지인지는 알려 주지 않는다. 기다릴 초만 본문과 Retry-After 에 싣는다.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.limits.attempts import TooManyAttempts


async def handle_too_many_attempts(request: Request, error: TooManyAttempts) -> JSONResponse:
    """허용된 횟수를 넘었다. 429."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            'detail': '요청이 너무 많습니다. 잠시 뒤에 다시 시도해 주세요.',
            'code': 'too_many_attempts',
            'retry_after': error.retry_after,
        },
        headers={'Retry-After': str(error.retry_after)},
    )
