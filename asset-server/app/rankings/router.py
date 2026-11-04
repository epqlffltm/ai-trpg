# asset-server/app/rankings/router.py

"""
캐릭터와 세계관의 랭킹 API(#985). 로그인하지 않아도 읽는다(공개 목록과 같다).

    GET /api/v1/asset/rankings/characters   최근 7일에 대화를 많이 시작한 캐릭터
    GET /api/v1/asset/rankings/worlds       최근 7일에 세션을 많이 시작한 세계관

  - 공개 목록에 나오는 것만이다. 볼 수 있는 등급만이고, 보는 사람의 설정(hide_adult, orientation)으로 거른다
  - 수는 몇 분마다 받아 온 것이다(app/stats/). 실행 중에 chat 과 story 서버를 부르지 않는다
  - limit 은 1~20, 기본 10 이다
"""

from typing import Annotated

from fastapi import APIRouter, Query, status
from server_core.auth.dependencies import OptionalUser

from app.characters.listings import to_public_summary as to_character_summary
from app.core.dependencies import ListingPreferences, Session
from app.preferences import shown_ratings
from app.rankings import repository
from app.rankings.schemas import CharacterRanking, RankedCharacter, RankedWorld, WorldRanking
from app.ratings import allowed_ratings
from app.stats.models import WorkKind
from app.worlds.listings import to_public_summary as to_world_summary

router = APIRouter(prefix='/rankings', tags=['rankings'])

# 랭킹의 "최근". chat 과 story 서버의 app/stats 와 같다
RECENT_DAYS = 7
DEFAULT_RANKING_SIZE = 10
MAX_RANKING_SIZE = 20

RankingSize = Annotated[int, Query(ge=1, le=MAX_RANKING_SIZE)]


@router.get('/characters', response_model=CharacterRanking, status_code=status.HTTP_200_OK)
async def rank_characters(
    user: OptionalUser, session: Session, preferences: ListingPreferences, limit: RankingSize = DEFAULT_RANKING_SIZE
) -> CharacterRanking:
    """최근 7일에 대화를 많이 시작한 캐릭터. 1위부터다."""
    ratings = shown_ratings(allowed_ratings(user), preferences)
    rows = await repository.ranked_characters(
        session, ratings, preferences.orientation_tag, limit, preferences.excluded
    )
    return CharacterRanking(
        recent_days=RECENT_DAYS,
        refreshed_at=await repository.refreshed_at(session, WorkKind.CHARACTER),
        items=[
            RankedCharacter(rank=index, starts=starts, character=to_character_summary(character, version))
            for index, (character, version, starts) in enumerate(rows, start=1)
        ],
    )


@router.get('/worlds', response_model=WorldRanking, status_code=status.HTTP_200_OK)
async def rank_worlds(
    user: OptionalUser, session: Session, preferences: ListingPreferences, limit: RankingSize = DEFAULT_RANKING_SIZE
) -> WorldRanking:
    """최근 7일에 세션을 많이 시작한 세계관. 1위부터다."""
    ratings = shown_ratings(allowed_ratings(user), preferences)
    rows = await repository.ranked_worlds(session, ratings, preferences.orientation_tag, limit, preferences.excluded)
    return WorldRanking(
        recent_days=RECENT_DAYS,
        refreshed_at=await repository.refreshed_at(session, WorkKind.WORLD),
        items=[
            RankedWorld(rank=index, starts=starts, world=to_world_summary(world, version))
            for index, (world, version, starts) in enumerate(rows, start=1)
        ],
    )
