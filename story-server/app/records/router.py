# story-server/app/records/router.py

"""
계정의 기록 API.

    GET /api/v1/story/endings?world_id=    그 세계관에서 내가 본 엔딩들(처음 본 차례)
    GET /api/v1/story/gallery?world_id=    그 세계관에서 내가 연 일러스트들(처음 연 차례). 갤러리의 story 탭이 읽는다
    GET /api/v1/story/achievements?world_id=        그 세계관에서 내가 받은 업적들(받은 차례)
    GET /api/v1/story/achievements/rates?world_id=  그 세계관의 업적마다 받은 사람의 수와 플레이한 사람의 수.
                                                    로그인하지 않아도 본다

달성률 말고는 로그인을 요구한다. 내 기록만 읽는다.
기록이 없거나 없는 세계관이면 빈 목록이다(세계관이 있는지 알리지 않는다).
달성률은 수만 준다. 누가 받았는지, 업적의 이름은 싣지 않는다(이름과 차례는 세계관의 소개에 있다).
주소들이 한 라우터에 있어 앱에는 한 번만 붙인다(app/main.py).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentViewer, Session
from app.records import repository
from app.records.illustrations import SceneKind
from app.records.models import AchievementRecord, EndingRecord, IllustrationUnlock
from app.records.schemas import (
    AchievementRate,
    AchievementRates,
    AchievementRecordList,
    AchievementRecordOut,
    EndingRecordList,
    EndingRecordOut,
    IllustrationList,
    IllustrationOut,
)

router = APIRouter(tags=['records'])

# 세계관을 고르는 질의 칸. 두 주소가 같다
WorldId = Annotated[uuid.UUID, Query(description='asset 서버의 세계관 id')]


def to_record(record: EndingRecord) -> EndingRecordOut:
    """본 엔딩 하나를 응답의 모양으로."""
    return EndingRecordOut(
        ending_id=record.ending_id, first_seen_at=record.first_seen_at, conversation_id=record.conversation_id
    )


def to_illustration(unlock: IllustrationUnlock) -> IllustrationOut:
    """연 일러스트 하나를 응답의 모양으로."""
    return IllustrationOut(
        kind=SceneKind(unlock.scene_kind),
        scene_id=unlock.scene_id,
        image_id=unlock.image_id,
        cast=list(unlock.cast),
        first_seen_at=unlock.first_seen_at,
        conversation_id=unlock.conversation_id,
    )


def to_achievement(record: AchievementRecord) -> AchievementRecordOut:
    """받은 업적 하나를 응답의 모양으로."""
    return AchievementRecordOut(
        achievement_id=record.achievement_id,
        name=record.name,
        description=record.description,
        image_id=record.image_id,
        earned_at=record.earned_at,
        conversation_id=record.conversation_id,
    )


@router.get('/endings', response_model=EndingRecordList, status_code=status.HTTP_200_OK)
async def list_endings(viewer: CurrentViewer, session: Session, world_id: WorldId) -> EndingRecordList:
    """그 세계관에서 내가 본 엔딩들."""
    records = await repository.endings_of(session, viewer.claims.user_id, world_id)
    return EndingRecordList(items=[to_record(record) for record in records])


@router.get('/gallery', response_model=IllustrationList, status_code=status.HTTP_200_OK)
async def list_illustrations(viewer: CurrentViewer, session: Session, world_id: WorldId) -> IllustrationList:
    """그 세계관에서 내가 연 일러스트들."""
    unlocks = await repository.illustrations_of(session, viewer.claims.user_id, world_id)
    return IllustrationList(items=[to_illustration(unlock) for unlock in unlocks])


@router.get('/achievements', response_model=AchievementRecordList, status_code=status.HTTP_200_OK)
async def list_achievements(viewer: CurrentViewer, session: Session, world_id: WorldId) -> AchievementRecordList:
    """그 세계관에서 내가 받은 업적들."""
    found = await repository.achievements_of(session, viewer.claims.user_id, world_id)
    return AchievementRecordList(items=[to_achievement(record) for record in found])


@router.get('/achievements/rates', response_model=AchievementRates, status_code=status.HTTP_200_OK)
async def read_achievement_rates(session: Session, world_id: WorldId) -> AchievementRates:
    """그 세계관의 업적마다 받은 사람의 수와 플레이한 사람의 수. 로그인하지 않아도 본다."""
    players = await repository.count_players(session, world_id)
    earned = await repository.count_earned(session, world_id)
    return AchievementRates(
        players=players, items=[AchievementRate(achievement_id=name, earned_count=count) for name, count in earned]
    )
