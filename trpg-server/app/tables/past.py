# trpg-server/app/tables/past.py

"""
떠난 사람이 자기가 떠난 테이블의 기록을 읽는다(#428).

앉은 사람의 길(app/tables/service.py 의 get_table)과 따로 둔다. 그 길은 "앉아 있어야 본다"를 그대로 지킨다.
여기서는 떠난 줄(table_departures)이 있어야 보고, 그 줄의 last_sequence 번까지의 이벤트만 준다.
떠난 뒤의 일은 보지 않는다. 라운드(rounds)는 열지 않는다. 라운드는 지금의 모습으로 보여서
떠날 때 열려 있던 라운드의 남의 선언과 결과가 새기 때문이다. 이벤트는 일어난 차례대로 적혀 있어 번호로 정확히 자른다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import repository as events
from app.events.models import TableEvent
from app.tables import repository
from app.tables.errors import TableNotFoundError
from app.tables.models import TableDeparture
from app.tables.repository import DepartureRow


async def list_past(
    session: AsyncSession, user_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[DepartureRow], int]:
    """내가 떠난 테이블의 한 쪽과 전체 개수. 최근에 떠난 것부터다."""
    rows = await repository.list_departures(session, user_id, limit, offset)
    total = await repository.count_departures(session, user_id)
    return rows, total


async def get_departure(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> TableDeparture:
    """내가 이 테이블을 떠난 줄. 떠난 적이 없으면 TableNotFoundError(404). 테이블이 있다는 것도 드러내지 않는다."""
    departure = await repository.find_departure(session, table_id, user_id)
    if departure is None:
        raise TableNotFoundError
    return departure


async def list_past_events(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, after: int, limit: int
) -> tuple[TableDeparture, list[TableEvent]]:
    """떠난 테이블의 이벤트 중 after 번 뒤의 것을, 떠난 때(last_sequence)까지만 순서대로 돌려준다."""
    departure = await get_departure(session, user_id, table_id)
    found = await events.list_after(session, table_id, after, limit, until=departure.last_sequence)
    return departure, found
