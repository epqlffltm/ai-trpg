# trpg-server/app/tables/time_limits.py

"""
테이블의 라운드 시간 제한을 바꾼다. 방장만 한다.

시간 제한은 라운드를 열 때 마감으로 굳는다(app/rounds/opener.py). 그래서 바꾼 값은 다음 라운드부터 쓴다.
지금 열려 있는 라운드의 마감은 그대로다. 앉은 사람들이 이미 보고 있는 마감이 갑자기 바뀌지 않는다.

바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.tables.models import GameTable
from app.tables.schemas import RoundTimeLimitUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_not_ended


async def change_round_time_limit(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: RoundTimeLimitUpdate
) -> GameTable:
    """
    방장이 라운드의 시간 제한을 바꾼다. null 이면 시간 제한을 없앤다.

    방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError.
    지금과 같은 값이면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)

    if data.round_time_limit == table.round_time_limit:
        return table

    table.round_time_limit = data.round_time_limit
    payload = {'round_time_limit': data.round_time_limit}
    recorder.record(session, table, EventType.ROUND_TIME_LIMIT_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)
