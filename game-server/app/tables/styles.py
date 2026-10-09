# game-server/app/tables/styles.py

"""
테이블의 서술 문체를 바꾼다. 방장만 한다.

문체는 GM 이 글을 쓰는 방식일 뿐이다. 판정과 상태는 건드리지 않는다. 그래서 진행 중에도 바꿀 수 있다.
바꾼 문체는 다음 서술부터 쓴다. 라운드가 닫기 시작할 때 그때의 문체를 라운드에 굳히기 때문이다(app/rounds).
이미 돌고 있는 서술은, 다시 맡겨도, 굳혀 둔 문체 그대로다.

바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.tables.models import GameTable
from app.tables.schemas import NarrationStyleUpdate
from app.tables.service import choose_narration_style, lock_seated, require_host, require_not_ended, save


async def change_narration_style(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: NarrationStyleUpdate
) -> GameTable:
    """
    방장이 서술 문체를 바꾼다. null 이면 판의 추천 문체로 돌린다.

    방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError.
    지금과 같은 문체면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)

    style = choose_narration_style(read_snapshot(table.content), data.narration_style)
    if style == table.narration_style:
        return table

    table.narration_style = style
    payload = {'narration_style': style}
    recorder.record(session, table, EventType.NARRATION_STYLE_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)
