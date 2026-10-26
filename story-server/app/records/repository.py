# story-server/app/records/repository.py

"""
계정의 기록을 읽고 쓴다. 커밋하지 않는다.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.records.illustrations import Unlock
from app.records.models import EndingRecord, IllustrationUnlock


async def add_ending(
    session: AsyncSession,
    owner_id: uuid.UUID,
    world_source: uuid.UUID,
    ending_id: str,
    conversation_id: uuid.UUID,
    now: datetime,
) -> None:
    """본 엔딩을 적는다. 이미 본 엔딩이면 그대로 둔다(처음 본 시각과 세션을 바꾸지 않는다)."""
    statement = (
        insert(EndingRecord)
        .values(
            owner_id=owner_id,
            world_source=world_source,
            ending_id=ending_id,
            conversation_id=conversation_id,
            first_seen_at=now,
        )
        .on_conflict_do_nothing(index_elements=['owner_id', 'world_source', 'ending_id'])
    )
    await session.execute(statement)


async def endings_of(session: AsyncSession, owner_id: uuid.UUID, world_source: uuid.UUID) -> list[EndingRecord]:
    """그 사람이 그 세계관에서 본 엔딩들. 처음 본 차례다."""
    query = (
        select(EndingRecord)
        .where(EndingRecord.owner_id == owner_id, EndingRecord.world_source == world_source)
        .order_by(EndingRecord.first_seen_at, EndingRecord.ending_id)
    )
    return list(await session.scalars(query))


async def add_illustrations(
    session: AsyncSession,
    owner_id: uuid.UUID,
    world_source: uuid.UUID,
    unlocks: Sequence[Unlock],
    conversation_id: uuid.UUID,
    now: datetime,
) -> None:
    """연 일러스트들을 적는다. 이미 연 장면이면 그대로 둔다(처음 연 때의 그림, 시각, 세션을 바꾸지 않는다)."""
    if not unlocks:
        return
    rows = [
        {
            'owner_id': owner_id,
            'world_source': world_source,
            'scene_kind': unlock.kind.value,
            'scene_id': unlock.scene_id,
            'image_id': unlock.image_id,
            'cast': list(unlock.cast),
            'conversation_id': conversation_id,
            'first_seen_at': now,
        }
        for unlock in unlocks
    ]
    statement = (
        insert(IllustrationUnlock)
        .values(rows)
        .on_conflict_do_nothing(index_elements=['owner_id', 'world_source', 'scene_kind', 'scene_id'])
    )
    await session.execute(statement)


async def illustrations_of(
    session: AsyncSession, owner_id: uuid.UUID, world_source: uuid.UUID
) -> list[IllustrationUnlock]:
    """그 사람이 그 세계관에서 연 일러스트들. 처음 연 차례다."""
    query = (
        select(IllustrationUnlock)
        .where(IllustrationUnlock.owner_id == owner_id, IllustrationUnlock.world_source == world_source)
        .order_by(IllustrationUnlock.first_seen_at, IllustrationUnlock.scene_kind, IllustrationUnlock.scene_id)
    )
    return list(await session.scalars(query))
