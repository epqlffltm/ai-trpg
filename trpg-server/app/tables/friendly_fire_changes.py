# trpg-server/app/tables/friendly_fire_changes.py

"""
앉은 사람끼리 해칠 수 있는 정도를 바꾼다(#803). 둘이다.

  - 테이블의 것: 방장만 바꾼다. 모집 중에도 진행 중에도 된다.
  - 자리의 것(자기를 겨누는 것을 받아들이는 정도): 앉은 사람이 자기 것만 바꾼다. 언제든 된다.

바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 보고, 누가 무엇을 받아들였는지 안다.
바꾸면 다음에 받는 선언부터, 그리고 이미 받은 선언도 라운드를 닫을 때 다시 본다(app/rounds/friendly_fire.py).
지금과 같으면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.tables.models import GameTable
from app.tables.schemas import FriendlyFireUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_not_ended


async def change_table_friendly_fire(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: FriendlyFireUpdate
) -> GameTable:
    """방장이 테이블의 것을 바꾼다. 방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError."""
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)

    if table.friendly_fire == data.friendly_fire:
        return table

    table.friendly_fire = data.friendly_fire
    payload = {'friendly_fire': data.friendly_fire.value}
    recorder.record(session, table, EventType.FRIENDLY_FIRE_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)


async def change_consent(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, data: FriendlyFireUpdate
) -> GameTable:
    """앉은 사람이 자기를 겨누는 것을 받아들이는 정도를 바꾼다. 끝난 테이블이면 TableConflictError."""
    table, member = await lock_seated(session, user_id, table_id)
    require_not_ended(table)

    if member.friendly_fire == data.friendly_fire:
        return table

    member.friendly_fire = data.friendly_fire
    payload = {'user_id': str(user_id), 'friendly_fire': data.friendly_fire.value}
    recorder.record(session, table, EventType.FRIENDLY_FIRE_CONSENT_CHANGED, actor_id=user_id, payload=payload)
    return await save(session, table)
