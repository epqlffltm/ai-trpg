# chat-server/app/achievements/router.py

"""
업적 API(docs/architecture/achievements.md 의 "chat").

    GET /api/v1/chat/achievements?character_id=        그 캐릭터에서 내가 받은 업적들(받은 차례)
    GET /api/v1/chat/achievements/rates?character_id=  그 캐릭터의 업적마다 받은 사람의 수와 대화한 사람의 수.
                                                       로그인하지 않아도 본다

달성률 말고는 로그인을 요구한다. 내 기록만 읽는다.
기록이 없거나 없는 캐릭터면 빈 목록이다(캐릭터가 있는지 알리지 않는다).
달성률은 수만 준다. 누가 받았는지, 업적의 이름은 싣지 않는다(이름과 차례는 캐릭터의 소개에 있다).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.achievements import repository
from app.achievements.models import AchievementRecord
from app.achievements.schemas import AchievementRate, AchievementRates, AchievementRecordList, AchievementRecordOut
from app.core.dependencies import CurrentViewer, Session

router = APIRouter(prefix='/achievements', tags=['achievements'])

# 캐릭터를 고르는 질의 칸. 두 주소가 같다
CharacterId = Annotated[uuid.UUID, Query(description='asset 서버의 캐릭터 id')]


def to_record(record: AchievementRecord) -> AchievementRecordOut:
    """받은 업적 하나를 응답의 모양으로."""
    return AchievementRecordOut(
        achievement_id=record.achievement_id,
        name=record.name,
        description=record.description,
        image_id=record.image_id,
        earned_at=record.earned_at,
        conversation_id=record.conversation_id,
    )


@router.get('', response_model=AchievementRecordList, status_code=status.HTTP_200_OK)
async def list_achievements(
    viewer: CurrentViewer, session: Session, character_id: CharacterId
) -> AchievementRecordList:
    """그 캐릭터에서 내가 받은 업적들."""
    found = await repository.achievements_of(session, viewer.claims.user_id, character_id)
    return AchievementRecordList(items=[to_record(record) for record in found])


@router.get('/rates', response_model=AchievementRates, status_code=status.HTTP_200_OK)
async def read_rates(session: Session, character_id: CharacterId) -> AchievementRates:
    """그 캐릭터의 업적마다 받은 사람의 수와 대화한 사람의 수. 로그인하지 않아도 본다."""
    players = await repository.count_players(session, character_id)
    earned = await repository.count_earned(session, character_id)
    return AchievementRates(
        players=players, items=[AchievementRate(achievement_id=name, earned_count=count) for name, count in earned]
    )
