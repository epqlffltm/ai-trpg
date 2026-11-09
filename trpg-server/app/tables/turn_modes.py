# trpg-server/app/tables/turn_modes.py

"""
라운드를 진행하는 방식(#287)을 바꾼다. 방장만 한다.

모집 중에만 바꾼다. 시작하면 고정이다. 차례의 순서와 바퀴는 시작할 때 처음 정한다(app/rounds/turn_order.py).
바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다.
HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.tables.models import GameTable
from app.tables.schemas import TurnModeUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_recruiting


async def change_turn_mode(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: TurnModeUpdate
) -> GameTable:
    """
    방장이 진행 방식을 바꾼다.

    방장이 아니면 NotHostError, 모집 중이 아니면 TableConflictError(not_recruiting). 지금과 같으면 아무것도 적지 않는다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_recruiting(table)

    if table.turn_mode == data.turn_mode:
        return table

    table.turn_mode = data.turn_mode
    payload = {'turn_mode': data.turn_mode.value}
    recorder.record(session, table, EventType.TURN_MODE_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)
