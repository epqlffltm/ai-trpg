# story-server/app/limits/routing.py

"""
API 가 요청 수 제한을 받는 길. 주소나 라우터에 의존성으로 건다(dependencies=[GENERATION_LIMIT] 처럼).

앱에 꽂아 둔 것(app.state.limiting)을 요청마다 꺼낸다. 테스트가 바꿔 꽂으면 그 뒤의 요청부터 바뀐 것을 쓴다.
로그인한 사람마다 센다. 로그인하지 않았으면 인증이 먼저 401 로 막는다.
"""

from fastapi import Depends, Request

from app.core.dependencies import CurrentViewer
from app.limits.setup import Limiting


def get_limiting(request: Request) -> Limiting:
    """앱에 꽂아 둔 요청 수 제한."""
    return request.app.state.limiting


async def count_generation(viewer: CurrentViewer, request: Request) -> None:
    """모델을 부르는 요청 한 번을 센다. 넘으면 TooManyAttempts(429)."""
    limiting = get_limiting(request)
    await limiting.limiter.count_attempt(limiting.limits.generations, str(viewer.claims.user_id))


async def count_write(viewer: CurrentViewer, request: Request) -> None:
    """모델을 부르지 않는 쓰기 한 번을 센다. 넘으면 TooManyAttempts(429)."""
    limiting = get_limiting(request)
    await limiting.limiter.count_attempt(limiting.limits.writes, str(viewer.claims.user_id))


async def count_transcript(viewer: CurrentViewer, request: Request) -> None:
    """기록 내려받기 한 번을 센다. 넘으면 TooManyAttempts(429)."""
    limiting = get_limiting(request)
    await limiting.limiter.count_attempt(limiting.limits.transcripts, str(viewer.claims.user_id))


# 주소나 라우터의 dependencies 에 넣는 것
GENERATION_LIMIT = Depends(count_generation)
WRITE_LIMIT = Depends(count_write)
TRANSCRIPT_LIMIT = Depends(count_transcript)
