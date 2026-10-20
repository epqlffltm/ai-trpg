# trpg-server/app/transcripts/reading.py

"""
기록을 받을 수 있는지 보고, 받을 이벤트를 쪽마다 읽는다(#403).

받는 사람은 둘이다.
  - 앉은 사람: 받기 시작한 때의 마지막 이벤트까지다. 받는 동안 테이블이 이어져도 파일의 끝은 그대로다.
  - 떠난 사람: 떠났다는 이벤트까지다(app/tables/past.py 와 같다). 떠난 뒤의 일은 받지 않는다.
둘 다 아니면 TableNotFoundError(404)다. 테이블이 있다는 것도 드러내지 않는다.

이벤트는 쪽마다 새 세션으로 읽는다. 큰 판도 메모리에 다 올리지 않고, 보내는 동안 DB 연결을 붙잡지 않는다.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assets.scenarios.snapshot import read_snapshot
from app.events import repository as events
from app.events.models import TableEvent
from app.tables import past, repository
from app.tables import service as tables
from app.tables.errors import TableNotFoundError
from app.transcripts.labels import Labels, labels_of

# 한 번에 읽는 이벤트의 수
PAGE_SIZE = 200


@dataclass(frozen=True)
class Cut:
    """받을 기록의 범위. until 번까지의 이벤트다. departed 면 떠난 사람이 받는 것이다. labels 는 판의 이름들이다."""

    table_id: uuid.UUID
    title: str
    until: int
    departed: bool
    labels: Labels


async def seated_cut(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> Cut:
    """앉은 사람이 받을 범위. 지금 테이블의 마지막 이벤트까지다. 앉지 않았으면 TableNotFoundError."""
    table = await tables.get_table(session, user_id, table_id)
    labels = labels_of(read_snapshot(table.content))
    return Cut(table_id=table.id, title=table.title, until=table.last_sequence, departed=False, labels=labels)


async def departed_cut(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> Cut:
    """떠난 사람이 받을 범위. 떠났다는 이벤트까지다. 떠난 적이 없으면 TableNotFoundError."""
    departure = await past.get_departure(session, user_id, table_id)
    heading = await repository.find_heading(session, table_id)
    if heading is None:
        raise TableNotFoundError
    title, content = heading
    labels = labels_of(read_snapshot(content))
    return Cut(table_id=table_id, title=title, until=departure.last_sequence, departed=True, labels=labels)


async def iter_events(
    session_factory: async_sessionmaker[AsyncSession], cut: Cut, page_size: int = PAGE_SIZE
) -> AsyncIterator[TableEvent]:
    """범위 안의 이벤트를 일어난 차례대로 하나씩 내놓는다. 쪽마다 세션을 열고 바로 닫는다."""
    after = 0
    while True:
        async with session_factory() as session:
            page = await events.list_after(session, cut.table_id, after, page_size, until=cut.until)
        for event in page:
            yield event
        if len(page) < page_size:
            return
        after = page[-1].sequence
