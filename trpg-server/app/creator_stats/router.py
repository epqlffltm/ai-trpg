# trpg-server/app/creator_stats/router.py

"""
제작자 숫자 API(#991). 로그인한 사람의 것만 읽는다. 남의 숫자를 읽는 길은 없다(남에게는 카드의 수만 보인다).

    GET /api/v1/game/me/stats/scenarios   내 시나리오마다 연 테이블의 수(모든 기간, 최근 7일)
"""

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser

from app.assets.routing import Session
from app.creator_stats.schemas import ScenarioStats
from app.creator_stats.service import scenario_stats

router = APIRouter(prefix='/me/stats', tags=['creator-stats'])


@router.get('/scenarios', response_model=ScenarioStats, status_code=status.HTTP_200_OK)
async def read_scenario_stats(user: CurrentUser, session: Session) -> ScenarioStats:
    """내 시나리오의 숫자. 최근 7일에 많이 연 것부터다."""
    return await scenario_stats(session, user.user_id)
