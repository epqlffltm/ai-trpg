# game-server/app/tables/ledger_draft_options.py

"""
서술한 장면에서 장부 초안을 쓸지 바꾼다. 방장만 한다.

켜면 라운드의 서술이 끝날 때마다 모델을 한 번 더 불러 초안을 쓴다(app/drafts/drafting.py). 그만큼 호출이 는다.
그래서 기본은 꺼 두고 방장이 고른다. 바꾼 뒤에 서술하는 라운드부터 따른다.

바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다. 초안은 방장만 보지만, 켜고 끈 것은 모두가 안다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.tables.models import GameTable
from app.tables.schemas import LedgerDraftsUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_not_ended


async def change_ledger_drafts(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: LedgerDraftsUpdate
) -> GameTable:
    """
    방장이 장부 초안을 쓸지 바꾼다.

    방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError.
    지금과 같으면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)

    if table.ledger_drafts == data.ledger_drafts:
        return table

    table.ledger_drafts = data.ledger_drafts
    recorder.record(session, table, EventType.LEDGER_DRAFTS_CHANGED, actor_id=host_id, payload=data.model_dump())
    return await save(session, table)
