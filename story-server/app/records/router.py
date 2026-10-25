# story-server/app/records/router.py

"""
계정의 기록 API.

    GET /api/v1/story/endings?world_id=    그 세계관에서 내가 본 엔딩들(처음 본 차례)

로그인을 요구한다. 내 기록만 읽는다. 기록이 없거나 없는 세계관이면 빈 목록이다(세계관이 있는지 알리지 않는다).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentViewer, Session
from app.records import repository
from app.records.models import EndingRecord
from app.records.schemas import EndingRecordList, EndingRecordOut

router = APIRouter(prefix='/endings', tags=['records'])


def to_record(record: EndingRecord) -> EndingRecordOut:
    """본 엔딩 하나를 응답의 모양으로."""
    return EndingRecordOut(
        ending_id=record.ending_id, first_seen_at=record.first_seen_at, conversation_id=record.conversation_id
    )


@router.get('', response_model=EndingRecordList, status_code=status.HTTP_200_OK)
async def list_endings(
    viewer: CurrentViewer,
    session: Session,
    world_id: Annotated[uuid.UUID, Query(description='asset 서버의 세계관 id')],
) -> EndingRecordList:
    """그 세계관에서 내가 본 엔딩들."""
    records = await repository.endings_of(session, viewer.claims.user_id, world_id)
    return EndingRecordList(items=[to_record(record) for record in records])
