# trpg-server/app/rankings/router.py

"""
시나리오의 랭킹 API(#985). 로그인하지 않아도 읽는다(공개 목록과 같다, #530).

    GET /api/v1/game/rankings/scenarios   최근 7일에 테이블을 많이 연 시나리오

  - 공개 목록에 나오는 것만이다. 볼 수 있는 등급만이고, 보는 사람의 설정(hide_adult, orientation)으로 거른다
  - 테이블이 이 서버에 있어 읽을 때 바로 센다(chat 과 story 의 수는 asset 서버가 몇 분마다 받아 온다)
  - limit 은 1~20, 기본 10 이다
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, status
from server_core.auth.dependencies import OptionalUser

from app.assets.ratings import allowed_ratings
from app.assets.routing import Session
from app.listings.repository import ListingFilter
from app.listings.router import HideAdultFilter, OrientationFilter, public_items
from app.rankings.repository import ranked_scenarios
from app.rankings.schemas import RankedScenario, ScenarioRanking

router = APIRouter(prefix='/rankings', tags=['rankings'])

# 랭킹의 "최근". asset 서버의 랭킹과 같다
RECENT_DAYS = 7
DEFAULT_RANKING_SIZE = 10
MAX_RANKING_SIZE = 20

RankingSize = Annotated[int, Query(ge=1, le=MAX_RANKING_SIZE)]


@router.get('/scenarios', response_model=ScenarioRanking, status_code=status.HTTP_200_OK)
async def rank_scenarios(
    user: OptionalUser,
    session: Session,
    limit: RankingSize = DEFAULT_RANKING_SIZE,
    hide_adult: HideAdultFilter = False,
    orientation: OrientationFilter = None,
) -> ScenarioRanking:
    """최근 7일에 테이블을 많이 연 시나리오. 1위부터다."""
    where = ListingFilter(hide_adult=hide_adult, orientation=orientation)
    since = datetime.now(UTC) - timedelta(days=RECENT_DAYS)
    rows = await ranked_scenarios(session, allowed_ratings(user), where, since, limit)
    return ScenarioRanking(
        recent_days=RECENT_DAYS,
        items=[
            RankedScenario(rank=index, starts=starts, listing=listing)
            for index, ((_, starts), listing) in enumerate(
                zip(rows, await public_items(session, [row for row, _ in rows]), strict=True), start=1
            )
        ],
    )
