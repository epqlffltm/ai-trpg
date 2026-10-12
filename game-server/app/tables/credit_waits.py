# game-server/app/tables/credit_waits.py

"""
크레딧이 모자란 사람을 기다리는 규칙을 바꾼다. 방장만 한다(#181).

규칙은 둘이다. 기다리는 시간(초)과, 지나면 그 사람을 자리에서 빼고 나머지로 서술하는가.
기다리는 일은 서버의 시계가 한다(app/rounds/credit_waits.py). 시계는 볼 때마다 테이블의 지금 규칙을 읽는다.
그래서 바꾼 값은 지금 기다리는 라운드에도 바로 쓴다. 기다리는 동안 방장이 사정을 보고 늘리거나 줄일 수 있다.

바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.tables.models import GameTable
from app.tables.schemas import CreditWaitUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_not_ended


def is_same(table: GameTable, data: CreditWaitUpdate) -> bool:
    """지금의 규칙과 같은가."""
    return (table.credit_wait_seconds, table.remove_short_payers) == (
        data.credit_wait_seconds,
        data.remove_short_payers,
    )


async def change_credit_wait(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: CreditWaitUpdate
) -> GameTable:
    """
    방장이 크레딧이 모자란 사람을 기다리는 규칙을 바꾼다.

    방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError.
    지금과 같으면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)

    if is_same(table, data):
        return table

    table.credit_wait_seconds = data.credit_wait_seconds
    table.remove_short_payers = data.remove_short_payers
    payload = data.model_dump()
    recorder.record(session, table, EventType.CREDIT_WAIT_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)
