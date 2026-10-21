# chat-server/app/api/readiness.py

"""
서버가 요청을 처리할 준비가 됐는지 확인하는 API. 로그인 없이 부를 수 있고, 내부 정보를 돌려주지 않는다.

프로세스가 살아 있는지(health.py)와는 묻는 것이 다르다. 여기는 서버가 기대는 DB 에 닿는지를 본다.
실패해도 관리 도구는 서버를 재시작하지 않는다. 요청을 잠시 보내지 않을 뿐이다.

확인 전체를 3초(READINESS_TIMEOUT_SECONDS)로 묶는다. 다른 네 서버와 같다.
확인한 결과를 메트릭 db_up 으로 적는다(1 이면 닿는다). compose 의 healthcheck 가 10초마다 부른다.
연결된 채 멈춘 DB 나, 풀이 가득 차 연결을 기다리는 동안(최대 30초)에도 확인 요청이 멈추지 않는다.

HEAD 도 받는다(본문 없이 같은 상태 코드).
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from server_core.database import get_session, ping_database
from server_core.observability.metrics import record_db_up
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.health import HealthResponse

logger = logging.getLogger(__name__)

# 확인 전체에 주는 시간(초). 지나면 준비되지 않은 것으로 본다. compose 의 healthcheck(5초)보다 짧다
READINESS_TIMEOUT_SECONDS = 3.0

router = APIRouter(tags=['health'])


@router.get(
    '/health/ready',
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {'model': HealthResponse}},
)
# HEAD 는 문서에 올리지 않는다(health.py 와 같은 까닭)
@router.head('/health/ready', status_code=status.HTTP_200_OK, include_in_schema=False)
async def check_readiness(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HealthResponse:
    """
    DB 에 3초 안에 닿으면 200, 아니면 503 을 돌려준다.

    왜 닿지 않는지는 응답에 싣지 않는다. 오류 문구에는 DB 의 주소와 계정 이름이 들어 있다.
    원인은 서버의 로그에 남긴다. 오류의 종류만 적는다.
    """
    problem = await find_problem_within(session, READINESS_TIMEOUT_SECONDS)
    record_db_up(problem is None)
    if problem is None:
        return HealthResponse(status='ok')
    logger.warning('준비되지 않았다: %s', problem)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status='unavailable')


async def find_problem_within(session: AsyncSession, seconds: float) -> str | None:
    """정한 시간 안에 DB 를 확인한다. 문제를 한 줄로 돌려주고, 없으면 None 이다."""
    try:
        return await asyncio.wait_for(find_problem(session), timeout=seconds)
    except TimeoutError:
        return f'{seconds:g}초 안에 확인이 끝나지 않았다'


async def find_problem(session: AsyncSession) -> str | None:
    """DB 에 닿아 본다. 닿지 않으면 오류의 종류를 돌려준다. 닿으면 None 이다."""
    try:
        await ping_database(session)
    except (SQLAlchemyError, OSError) as exc:
        # OSError 는 연결 거부와 시간 초과를 포함한다
        return f'DB 에 닿지 않는다({type(exc).__name__})'
    return None
