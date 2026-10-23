# trpg-server/app/calendar/router.py

"""
테이블의 시계 API. 앉은 사람이 지금 시각과 다음 라운드에 흐를 시간을 본다.

흐를 시간은 엔진이 정한다(판의 기본, 길을 가기, 쉬기, 기다리기). 사람이 정하는 길은 없다(#367).

길은 테이블 아래다(/tables/{id}/clock).
테이블의 예외(없음, 방장 아님, 진행 중 아님)는 테이블의 처리기가 응답으로 바꾼다.
"""

import uuid

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser

from app.assets.routing import Session
from app.calendar.responses import to_clock
from app.calendar.schemas import ClockOut
from app.tables import service as table_service

router = APIRouter(prefix='/tables', tags=['calendar'])


@router.get('/{table_id}/clock', response_model=ClockOut, status_code=status.HTTP_200_OK)
async def get_clock(table_id: uuid.UUID, user: CurrentUser, session: Session) -> ClockOut:
    """
    테이블의 게임 안의 지금 시각과 다음 라운드가 열릴 때 흐를 시간. 앉은 사람 모두가 본다.

    시작 전에는 판의 시작 시각이다. 라운드가 열릴 때마다 흐른다(첫 라운드는 시작 시각에 열린다).
    """
    table = await table_service.get_table(session, user.user_id, table_id)
    return to_clock(table)
