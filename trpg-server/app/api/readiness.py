# trpg-server/app/api/readiness.py

"""
서버가 요청을 처리할 준비가 됐는지 확인하는 API. 로그인 없이 부를 수 있고, 내부 정보를 돌려주지 않는다.

프로세스가 살아 있는지(health.py)와는 묻는 것이 다르다.
여기는 서버가 기대는 것들에 닿는지를 본다. DB 와, REDIS_URL 이 있으면 Redis 다(#258).
Redis 를 쓰면 로비 비밀번호와 채팅의 시도 제한이 Redis 에 닿지 못할 때 닫힌 쪽으로 실패한다(503).
그래서 Redis 도 요청을 처리하는 데 꼭 필요하다. REDIS_URL 이 없으면 서버 안의 메모리로 세므로 보지 않는다.
실패해도 관리 도구는 서버를 재시작하지 않는다. 요청을 잠시 보내지 않을 뿐이다.

확인 전체를 3초(READINESS_TIMEOUT_SECONDS)로 묶는다. 결제·게시판 서버와 같다.
DB 에 닿았는지를 메트릭 db_up 으로 적는다(1 이면 닿는다). Redis 만 닿지 않으면 503 이어도 db_up 은 1 이다.
compose 의 healthcheck 가 10초마다 부른다.
연결된 채 멈춘 DB 나, 풀이 가득 차 연결을 기다리는 동안(최대 30초)에도 확인 요청이 멈추지 않는다.

HEAD 도 받는다(본문 없이 같은 상태 코드). 요청이 끝난 줄은 성공이면 debug, 503 이면 warning 이다.
"""

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Request, Response, status
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.health import HealthResponse
from app.core.database import get_session, ping_database
from app.observability.metrics import record_db_up

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
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HealthResponse:
    """
    기대는 것들에 3초 안에 모두 닿으면 200, 아니면 503 을 돌려준다.

    왜 닿지 않는지는 응답에 싣지 않는다. 오류 문구에는 DB 와 Redis 의 주소, 계정 이름이 들어 있다.
    원인은 서버의 로그에 남긴다. 오류의 종류만 적는다.
    """
    found = await find_problem_within(session, request.app.state.redis, READINESS_TIMEOUT_SECONDS)
    record_db_up(found.database_reachable)
    if found.problem is None:
        return HealthResponse(status='ok')
    logger.warning('준비되지 않았다: %s', found.problem)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status='unavailable')


@dataclass(frozen=True)
class Readiness:
    """확인한 결과. DB 에 닿았는가와, 처음 닿지 않은 것의 한 줄(다 닿으면 None)."""

    database_reachable: bool
    problem: str | None


async def find_problem_within(session: AsyncSession, client: redis.Redis | None, seconds: float) -> Readiness:
    """
    정한 시간 안에 DB 와(쓰면) Redis 를 차례로 확인한다. 둘이 시간을 나눠 쓴다.

    DB 가 닿지 않거나 DB 를 보다가 시간이 다 되면 DB 에 닿지 않은 것이다. Redis 의 문제는 DB 와 따로다.
    """
    deadline = asyncio.get_running_loop().time() + seconds
    problem = await problem_by(database_problem(session), deadline, seconds)
    if problem is not None:
        return Readiness(database_reachable=False, problem=problem)
    return Readiness(database_reachable=True, problem=await problem_by(redis_problem(client), deadline, seconds))


async def problem_by(check: Awaitable[str | None], deadline: float, seconds: float) -> str | None:
    """확인 하나를 deadline(이벤트 루프의 시각)까지 기다린다. 넘으면 정한 시간(seconds)을 적은 한 줄이다."""
    try:
        async with asyncio.timeout_at(deadline):
            return await check
    except TimeoutError:
        return f'{seconds:g}초 안에 확인이 끝나지 않았다'


async def database_problem(session: AsyncSession) -> str | None:
    """DB 에 닿아 본다. 닿지 않으면 오류의 종류를 돌려준다. 닿으면 None 이다."""
    try:
        await ping_database(session)
    except (SQLAlchemyError, OSError) as exc:
        # OSError 는 연결 거부와 시간 초과를 포함한다
        return f'DB 에 닿지 않는다({type(exc).__name__})'
    return None


async def redis_problem(client: redis.Redis | None) -> str | None:
    """Redis 를 쓰면 닿아 본다. 닿지 않으면 오류의 종류를 돌려준다. 닿거나 쓰지 않으면 None 이다."""
    if client is None:
        return None
    try:
        await client.ping()
    except (RedisError, OSError) as exc:
        return f'Redis 에 닿지 않는다({type(exc).__name__})'
    return None
