# asset-server/app/creator_stats/router.py

"""
제작자 숫자 API(#991). 로그인한 사람의 것만 읽는다. 남의 숫자를 읽는 길은 없다(남에게는 카드의 수만 보인다).

    GET /api/v1/asset/me/stats/characters   내 캐릭터마다 대화를 시작한 수(모든 기간, 최근 7일)
    GET /api/v1/asset/me/stats/worlds       내 세계관마다 세션을 시작한 수

수는 한 시간까지 늦다(app/stats/ 가 받아 온 것이다).
"""

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser

from app.core.dependencies import Session
from app.creator_stats.schemas import WorkStats
from app.creator_stats.service import work_stats
from app.stats.models import WorkKind

router = APIRouter(prefix='/me/stats', tags=['creator-stats'])


@router.get('/characters', response_model=WorkStats, status_code=status.HTTP_200_OK)
async def read_character_stats(user: CurrentUser, session: Session) -> WorkStats:
    """내 캐릭터의 숫자. 최근 7일에 많이 시작한 것부터다."""
    return await work_stats(session, WorkKind.CHARACTER, user.user_id)


@router.get('/worlds', response_model=WorkStats, status_code=status.HTTP_200_OK)
async def read_world_stats(user: CurrentUser, session: Session) -> WorkStats:
    """내 세계관의 숫자. 최근 7일에 많이 시작한 것부터다."""
    return await work_stats(session, WorkKind.WORLD, user.user_id)
