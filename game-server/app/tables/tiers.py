# game-server/app/tables/tiers.py

"""
테이블의 서술 등급(app/rounds/tiers.py)을 바꾼다. 방장만 한다.

등급은 라운드를 열 때 그 라운드의 것으로 굳는다(app/rounds/opener.py). 그래서 바꾼 값은 다음 라운드부터 쓴다.
지금 열려 있는 라운드는 연 때의 등급으로 값을 걸어 두었다.
그 라운드를 바꾼 등급으로 서술하면 낸 값과 받은 서술이 어긋난다.

이 서버가 내주는 등급만 고를 수 있다(state.require_offered).
바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.rounds.tiers import NarrationTier
from app.tables.models import GameTable
from app.tables.schemas import NarrationTierUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_not_ended, require_offered


async def change_narration_tier(
    session: AsyncSession,
    host_id: uuid.UUID,
    table_id: uuid.UUID,
    data: NarrationTierUpdate,
    offered: frozenset[NarrationTier],
) -> GameTable:
    """
    방장이 서술 등급을 바꾼다. offered 는 이 서버가 내주는 등급들이다.

    방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError, 내주지 않는 등급이면 TableOptionError.
    지금과 같은 값이면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)
    require_offered(data.narration_tier, offered)

    if data.narration_tier == table.narration_tier:
        return table

    table.narration_tier = data.narration_tier
    payload = {'narration_tier': data.narration_tier}
    recorder.record(session, table, EventType.NARRATION_TIER_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)
