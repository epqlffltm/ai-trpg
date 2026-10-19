# trpg-server/app/calendar/router.py

"""
테이블의 시계 API. 앉은 사람이 지금 시각을 보고, 방장이 다음 라운드에 흐를 시간을 정한다.

길은 테이블 아래다(/tables/{id}/clock).
테이블의 예외(없음, 방장 아님, 진행 중 아님)는 테이블의 처리기가 응답으로 바꾼다.
"""

import uuid

from fastapi import APIRouter, status

from app.assets.routing import Session
from app.auth.dependencies import CurrentUser
from app.calendar import clock, service, state
from app.calendar.schemas import ClockOut, StepChange
from app.tables import service as table_service
from app.tables.models import GameTable

router = APIRouter(prefix='/tables', tags=['calendar'])


def to_clock(table: GameTable) -> ClockOut:
    """테이블의 시계를 응답으로 바꾼다."""
    now = clock.read_time(table.clock.minutes)
    return ClockOut(
        day=now.day,
        hour=now.hour,
        minute=now.minute,
        time_of_day=now.time_of_day,
        next_step_minutes=state.next_step(table),
        default_step_minutes=state.default_step(table),
        step_changed=table.clock.next_step_minutes is not None,
    )


@router.get('/{table_id}/clock', response_model=ClockOut, status_code=status.HTTP_200_OK)
async def get_clock(table_id: uuid.UUID, user: CurrentUser, session: Session) -> ClockOut:
    """
    테이블의 게임 안의 지금 시각과 다음 라운드가 열릴 때 흐를 시간. 앉은 사람 모두가 본다.

    시작 전에는 판의 시작 시각이다. 라운드가 열릴 때마다 흐른다(첫 라운드는 시작 시각에 열린다).
    """
    table = await table_service.get_table(session, user.user_id, table_id)
    return to_clock(table)


@router.put('/{table_id}/clock/step', response_model=ClockOut, status_code=status.HTTP_200_OK)
async def set_step(table_id: uuid.UUID, data: StepChange, user: CurrentUser, session: Session) -> ClockOut:
    """
    방장이 다음 라운드가 열릴 때 흐를 시간(분)을 정한다. 진행 중에만 된다. null 이면 판의 기본으로.

    한 번 쓰면 판의 기본으로 돌아간다. 모두에게 이벤트(clock_step_changed)가 간다. AI 는 시계를 바꾸지 못한다.
    """
    table = await service.set_step(session, user.user_id, table_id, data.minutes)
    return to_clock(table)
