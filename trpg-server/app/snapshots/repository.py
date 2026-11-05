# trpg-server/app/snapshots/repository.py

"""
장면 그림의 SQL(#983). 커밋하지 않는다.

청구의 상태는 "지금 이 상태일 때만" 옮긴다(move_billing). 정리 작업과 한 장의 길이 같은 줄을 함께 만져도 한쪽만 옮긴다.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.snapshots.models import DUE_STATUSES, OPEN_STATUSES, SnapshotBilling, TableSnapshot


def add(session: AsyncSession, snapshot: TableSnapshot) -> None:
    """새 행을 세션에 올린다."""
    session.add(snapshot)


async def get(session: AsyncSession, snapshot_id: uuid.UUID) -> TableSnapshot | None:
    """한 장. 없으면 None."""
    return await session.get(TableSnapshot, snapshot_id, populate_existing=True)


async def of_table(session: AsyncSession, table_id: uuid.UUID) -> list[TableSnapshot]:
    """그 테이블의 그림들. 만든 차례다."""
    query = (
        select(TableSnapshot)
        .where(TableSnapshot.table_id == table_id)
        .order_by(TableSnapshot.created_at, TableSnapshot.id)
    )
    return list(await session.scalars(query))


async def find_in_table(session: AsyncSession, table_id: uuid.UUID, snapshot_id: uuid.UUID) -> TableSnapshot | None:
    """그 테이블의 그림 한 장. 다른 테이블의 것이면 None."""
    query = select(TableSnapshot).where(TableSnapshot.id == snapshot_id, TableSnapshot.table_id == table_id)
    return await session.scalar(query)


async def move_billing(
    session: AsyncSession, snapshot_id: uuid.UUID, expected: frozenset[SnapshotBilling], values: dict[str, object]
) -> bool:
    """청구의 상태가 expected 중 하나일 때만 values 로 고친다. 고쳤으면 True."""
    statement = (
        update(TableSnapshot)
        .where(TableSnapshot.id == snapshot_id, TableSnapshot.billing_status.in_([status.value for status in expected]))
        .values(**values)
        .returning(TableSnapshot.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).first() is not None


async def find_due(session: AsyncSession, now: datetime, stale: timedelta, limit: int) -> list[TableSnapshot]:
    """
    결제 서버에 맡길 차례가 된 청구들. 확정할 것과 돌려줄 것 가운데 때가 된 것, 그리고 그리는 도중에 오래 남은 것
    (서버가 꺼졌다. 부르는 쪽이 실패로 적고 돌려준다).
    """
    due = TableSnapshot.billing_status.in_([status.value for status in DUE_STATUSES]) & or_(
        TableSnapshot.next_settle_at.is_(None), TableSnapshot.next_settle_at <= now
    )
    abandoned = TableSnapshot.billing_status.in_([status.value for status in OPEN_STATUSES]) & (
        TableSnapshot.created_at < now - stale
    )
    query = select(TableSnapshot).where(or_(due, abandoned)).order_by(TableSnapshot.created_at).limit(limit)
    return list(await session.scalars(query))


async def remove_settled(session: AsyncSession, snapshot_id: uuid.UUID, settled: frozenset[SnapshotBilling]) -> bool:
    """청구가 끝난(settled 중 하나인) 그림 한 장의 기록을 지운다. 지웠으면 True."""
    statement = (
        delete(TableSnapshot)
        .where(TableSnapshot.id == snapshot_id, TableSnapshot.billing_status.in_([status.value for status in settled]))
        .returning(TableSnapshot.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).first() is not None
