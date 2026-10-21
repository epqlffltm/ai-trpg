# trpg-server/app/tables/references.py

"""
서술에 참고 자료(#482, SRD 같은 바깥 자료)를 넣을지 바꾼다. 방장만 한다.

모집 중에만 바꾼다. 시작하면 고정이다(2026-10-21 유저 결정). 앉는 것이 그 서술에 대한 동의다.
값은 더 받지 않는다. 참고 자료는 입력 예산 안에서 로어북의 남은 자리에만 들어간다(app/rounds/budget.py).
켜려면 판의 세계관이 허용해야 한다(app/references/policy.py). 끄는 것은 늘 된다.

바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다.
HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.references.policy import references_allowed
from app.tables.errors import TableOptionError
from app.tables.models import GameTable
from app.tables.schemas import ReferencesUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_recruiting


def require_allowed(table: GameTable, enabled: bool) -> None:
    """켜려는데 이 테이블의 판(복사본)의 세계관이 허용하지 않으면 TableOptionError(references_enabled)."""
    if enabled and not references_allowed(read_snapshot(table.content)):
        raise TableOptionError('references_enabled')


async def change_references(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: ReferencesUpdate
) -> GameTable:
    """
    방장이 참고 자료를 서술에 넣을지 바꾼다.

    방장이 아니면 NotHostError, 모집 중이 아니면 TableConflictError(not_recruiting),
    허용하지 않는 판에서 켜려 했으면 TableOptionError. 지금과 같으면 아무것도 적지 않는다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_recruiting(table)
    require_allowed(table, data.references_enabled)

    if table.references_enabled == data.references_enabled:
        return table

    table.references_enabled = data.references_enabled
    recorder.record(session, table, EventType.REFERENCES_CHANGED, actor_id=host_id, payload=data.model_dump())
    return await save(session, table)
