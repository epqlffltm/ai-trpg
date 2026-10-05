# game-server/app/events/repository.py

"""
이벤트를 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

고치는 함수와 지우는 함수가 없다. 이벤트는 덧붙이기만 한다.
읽는 함수는 모두 테이블의 ID 를 받는다. 다른 테이블의 이벤트가 딸려 나올 길이 없다.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import EventType, TableEvent


def add_event(session: AsyncSession, event: TableEvent) -> None:
    """새 이벤트를 세션에 올린다."""
    session.add(event)


async def find_latest(session: AsyncSession, table_id: uuid.UUID, type_: EventType) -> TableEvent | None:
    """테이블의 이 종류의 이벤트 중 가장 최근 것을 찾는다. 없으면 None."""
    query = (
        select(TableEvent)
        .where(TableEvent.table_id == table_id, TableEvent.type == type_)
        .order_by(TableEvent.sequence.desc())
        .limit(1)
    )
    return await session.scalar(query)


async def list_after(session: AsyncSession, table_id: uuid.UUID, after: int, limit: int) -> list[TableEvent]:
    """
    테이블의 이벤트 중 after 번 뒤의 것을 순서대로 돌려준다. limit 개까지다.

    몇 번째부터(offset)가 아니라 어느 번호 뒤(after)로 자른다.
    읽는 사이에 새 이벤트가 생겨도 같은 것이 두 번 나오거나 빠지지 않는다. 뒤쪽을 읽을 때도 느려지지 않는다.
    """
    query = (
        select(TableEvent)
        .where(TableEvent.table_id == table_id, TableEvent.sequence > after)
        .order_by(TableEvent.sequence)
        .limit(limit)
    )
    return list(await session.scalars(query))
