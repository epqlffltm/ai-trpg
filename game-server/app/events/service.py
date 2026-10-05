# game-server/app/events/service.py

"""
이벤트를 읽는다. 적는 것은 app/events/recorder.py 가 한다.

HTTP 를 모른다. SQL 을 모른다.

테이블의 규칙을 그대로 따른다(app/tables/service.py). 이벤트는 테이블에 앉은 사람만 본다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import repository
from app.events.models import TableEvent
from app.tables import service as tables
from app.tables.models import GameTable


async def list_events(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, after: int, limit: int
) -> tuple[GameTable, list[TableEvent]]:
    """
    자기가 앉아 있는 테이블의 이벤트 중 after 번 뒤의 것을 순서대로 돌려준다. 테이블도 함께 돌려준다.

    앉지 않았으면 TableNotFoundError. 내보내진 사람은 그 뒤로 읽지 못한다.
    """
    table = await tables.get_table(session, user_id, table_id)
    events = await repository.list_after(session, table_id, after, limit)
    return table, events
