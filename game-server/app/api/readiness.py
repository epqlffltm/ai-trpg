# game-server/app/api/readiness.py

"""
서버가 요청을 처리할 준비가 됐는지 확인하는 API. 로그인 없이 부를 수 있고, 내부 정보를 돌려주지 않는다.

프로세스가 살아 있는지(health.py)와는 묻는 것이 다르다.
여기는 서버가 기대는 것들(지금은 DB)에 닿는지를 본다.
실패해도 관리 도구는 서버를 재시작하지 않는다. 요청을 잠시 보내지 않을 뿐이다.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.health import HealthResponse
from app.core.database import get_session, ping_database

logger = logging.getLogger(__name__)

router = APIRouter(tags=['health'])


@router.get(
    '/health/ready',
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {'model': HealthResponse}},
)
async def check_readiness(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HealthResponse:
    """
    DB 에 닿으면 200, 닿지 않으면 503 을 돌려준다.

    왜 닿지 않는지는 응답에 싣지 않는다. 오류 문구에는 DB 주소와 계정 이름이 들어 있다.
    원인은 서버의 로그에 남긴다.
    """
    try:
        await ping_database(session)
    except (SQLAlchemyError, OSError) as exc:
        # OSError 는 연결 거부와 시간 초과를 포함한다
        logger.warning('DB 에 닿지 않는다: %s', type(exc).__name__)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status='unavailable')
    return HealthResponse(status='ok')
