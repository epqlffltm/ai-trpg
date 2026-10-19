# trpg-server/app/calendar/service.py

"""
방장이 테이블의 시계를 다룬다. 지금은 다음 라운드가 열릴 때 흐를 시간을 정하는 것 하나다.

시각을 곧바로 바꾸지는 않는다(달력 1단계). 흐를 시간을 정하면 다음 라운드가 열릴 때 엔진이 흘린다.
"하룻밤 쉰다"는 다음 걸음을 8시간으로 두는 것이다. AI GM 은 시계를 건드리지 못한다.

HTTP 를 모른다. 테이블을 잠그고 한다. 라운드가 열리는 것과 엇갈려도 정한 값이 반쯤 쓰이지 않는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.calendar import state
from app.events import recorder
from app.events.models import EventType
from app.tables.item_grants import require_playing
from app.tables.models import GameTable
from app.tables.service import lock_seated, save
from app.tables.state import require_host


def describe_step(previous: int, table: GameTable) -> dict:
    """바꾼 것을 이벤트에 적을 모양. 흐를 시간이 몇 분에서 몇 분으로, 판의 기본으로 되돌렸는가."""
    return {
        'previous': previous,
        'next_step_minutes': state.next_step(table),
        'default': table.clock.next_step_minutes is None,
    }


async def set_step(session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, minutes: int | None) -> GameTable:
    """
    방장이 다음 라운드가 열릴 때 흐를 시간을 정한다. None 이면 판의 기본으로 되돌린다.

    방장이 아니면 NotHostError, 진행 중이 아니면 TableConflictError(not_playing).
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_playing(table)
    previous = state.next_step(table)
    state.set_next_step(table, minutes)
    payload = describe_step(previous, table)
    recorder.record(session, table, EventType.CLOCK_STEP_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)
