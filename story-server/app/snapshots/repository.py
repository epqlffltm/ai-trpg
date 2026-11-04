# story-server/app/snapshots/repository.py

"""
장면 그림의 SQL(#983). 커밋하지 않는다.

청구의 상태는 "지금 이 상태일 때만" 옮긴다(move_billing). 정리 작업과 한 장의 길이 같은 줄을 함께 만져도 한쪽만 옮긴다.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ImportedWorld
from app.conversations.repository import visible
from app.ratings import Rating
from app.snapshots.models import Snapshot, SnapshotOutcome
from app.turns.models import DUE_STATUSES, OPEN_STATUSES, BillingStatus


def add(session: AsyncSession, snapshot: Snapshot) -> None:
    """새 행을 세션에 올린다."""
    session.add(snapshot)


async def get(session: AsyncSession, snapshot_id: uuid.UUID) -> Snapshot | None:
    """한 장. 없으면 None."""
    return await session.get(Snapshot, snapshot_id, populate_existing=True)


async def of_conversation(session: AsyncSession, conversation_id: uuid.UUID) -> list[Snapshot]:
    """그 세션의 그림들. 만든 차례다."""
    query = select(Snapshot).where(Snapshot.conversation_id == conversation_id).order_by(Snapshot.created_at)
    return list(await session.scalars(query))


async def kept_images(session: AsyncSession, conversation_id: uuid.UUID) -> list[uuid.UUID]:
    """그 세션의 그림 가운데 asset 에 맡긴 것들의 id."""
    query = select(Snapshot.image_id).where(Snapshot.conversation_id == conversation_id, Snapshot.image_id.is_not(None))
    return [image_id for image_id in await session.scalars(query) if image_id is not None]


def kept_of(owner_id: uuid.UUID, ratings: Sequence[Rating]) -> Select:
    """이 사람의 다 그린 그림들. 지우지 않았고 볼 수 있는 등급의 세션의 것만이다. (세션, 판의 사본, 그림)을 고른다."""
    return (
        visible(owner_id, ratings)
        .add_columns(Snapshot)
        .join(Snapshot, Snapshot.conversation_id == Conversation.id)
        .where(
            Snapshot.owner_id == owner_id,
            Snapshot.outcome == SnapshotOutcome.READY,
            Snapshot.image_id.is_not(None),
        )
    )


async def list_kept(
    session: AsyncSession, owner_id: uuid.UUID, ratings: Sequence[Rating], limit: int, offset: int
) -> tuple[list[tuple[Snapshot, Conversation, ImportedWorld]], int]:
    """이 사람의 다 그린 그림들의 한 쪽과 전체 개수. 최근에 만든 것부터다."""
    query = kept_of(owner_id, ratings)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    page = query.order_by(Snapshot.created_at.desc(), Snapshot.id.desc()).limit(limit).offset(offset)
    rows = await session.execute(page)
    return [(row[2], row[0], row[1]) for row in rows], total or 0


async def drawing(session: AsyncSession, conversation_id: uuid.UUID) -> Snapshot | None:
    """그 세션에서 그리는 중인 것. 없으면 None."""
    query = select(Snapshot).where(Snapshot.conversation_id == conversation_id, Snapshot.outcome.is_(None))
    return await session.scalar(query)


async def move_billing(
    session: AsyncSession, snapshot_id: uuid.UUID, expected: frozenset[BillingStatus], values: dict[str, object]
) -> bool:
    """청구의 상태가 expected 중 하나일 때만 values 로 고친다. 고쳤으면 True."""
    statement = (
        update(Snapshot)
        .where(Snapshot.id == snapshot_id, Snapshot.billing_status.in_([status.value for status in expected]))
        .values(**values)
        .returning(Snapshot.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).first() is not None


async def find_due(session: AsyncSession, now: datetime, stale: timedelta, limit: int) -> list[Snapshot]:
    """
    결제 서버에 맡길 차례가 된 청구들. 확정할 것과 돌려줄 것 가운데 때가 된 것, 그리고 그리는 도중에 오래 남은 것
    (서버가 꺼졌다. 부르는 쪽이 실패로 적고 돌려준다).
    """
    due = Snapshot.billing_status.in_([status.value for status in DUE_STATUSES]) & or_(
        Snapshot.next_settle_at.is_(None), Snapshot.next_settle_at <= now
    )
    abandoned = Snapshot.billing_status.in_([status.value for status in OPEN_STATUSES]) & (
        Snapshot.created_at < now - stale
    )
    query = select(Snapshot).where(or_(due, abandoned)).order_by(Snapshot.created_at).limit(limit)
    return list(await session.scalars(query))
