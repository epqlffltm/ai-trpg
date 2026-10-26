# story-server/app/records/router.py

"""
계정의 기록 API.

    GET /api/v1/story/endings?world_id=    그 세계관에서 내가 본 엔딩들(처음 본 차례)
    GET /api/v1/story/gallery?world_id=    그 세계관에서 내가 연 일러스트들(처음 연 차례). 갤러리의 story 탭이 읽는다

로그인을 요구한다. 내 기록만 읽는다. 기록이 없거나 없는 세계관이면 빈 목록이다(세계관이 있는지 알리지 않는다).
두 주소가 한 라우터에 있어 앱에는 한 번만 붙인다(app/main.py).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentViewer, Session
from app.records import repository
from app.records.illustrations import SceneKind
from app.records.models import EndingRecord, IllustrationUnlock
from app.records.schemas import EndingRecordList, EndingRecordOut, IllustrationList, IllustrationOut

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
