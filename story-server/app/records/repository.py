# story-server/app/records/repository.py

"""
계정의 기록을 읽고 쓴다. 커밋하지 않는다.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.world import Achievement
from app.records.illustrations import Unlock
from app.records.models import AchievementRecord, EndingRecord, IllustrationUnlock, WorldPlayer


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


async def mark_played(session: AsyncSession, owner_id: uuid.UUID, world_source: uuid.UUID, now: datetime) -> None:
    """그 사람이 그 세계관을 플레이했다고 적는다. 이미 적혔으면 그대로 둔다(처음 플레이한 때를 바꾸지 않는다)."""
    statement = (
        insert(WorldPlayer)
        .values(owner_id=owner_id, world_source=world_source, first_played_at=now)
        .on_conflict_do_nothing(index_elements=['owner_id', 'world_source'])
    )
    await session.execute(statement)


async def achievement_ids_of(session: AsyncSession, owner_id: uuid.UUID, world_source: uuid.UUID) -> frozenset[str]:
    """그 사람이 그 세계관에서 받은 업적의 id 들."""
    query = select(AchievementRecord.achievement_id).where(
        AchievementRecord.owner_id == owner_id, AchievementRecord.world_source == world_source
    )
    return frozenset(await session.scalars(query))


async def add_achievements(
    session: AsyncSession,
    owner_id: uuid.UUID,
    world_source: uuid.UUID,
    achievements: Sequence[Achievement],
    conversation_id: uuid.UUID | None,
    now: datetime,
) -> frozenset[str]:
    """
    받은 업적들을 적고, 이번에 새로 적힌 것의 id 를 돌려준다.
    이미 받은 것은 그대로 둔다(처음 받은 때, 이름, 세션을 바꾸지 않는다).
    두 세션이 함께 줘도 하나만 적히고 하나만 알린다.
    """
    if not achievements:
        return frozenset()
    rows = [
        {
            'owner_id': owner_id,
            'world_source': world_source,
            'achievement_id': achievement.id,
            'name': achievement.name,
            'description': achievement.description,
            'image_id': achievement.image_id,
            'conversation_id': conversation_id,
            'earned_at': now,
        }
        for achievement in achievements
    ]
    statement = (
        insert(AchievementRecord)
        .values(rows)
        .on_conflict_do_nothing(index_elements=['owner_id', 'world_source', 'achievement_id'])
        .returning(AchievementRecord.achievement_id)
    )
    return frozenset(await session.scalars(statement))


async def achievements_of(
    session: AsyncSession, owner_id: uuid.UUID, world_source: uuid.UUID
) -> list[AchievementRecord]:
    """그 사람이 그 세계관에서 받은 업적들. 받은 차례다."""
    query = (
        select(AchievementRecord)
        .where(AchievementRecord.owner_id == owner_id, AchievementRecord.world_source == world_source)
        .order_by(AchievementRecord.earned_at, AchievementRecord.achievement_id)
    )
    return list(await session.scalars(query))


async def count_players(session: AsyncSession, world_source: uuid.UUID) -> int:
    """그 세계관을 플레이한 사람의 수."""
    query = select(func.count()).select_from(WorldPlayer).where(WorldPlayer.world_source == world_source)
    return await session.scalar(query) or 0


async def count_earned(session: AsyncSession, world_source: uuid.UUID) -> list[tuple[str, int]]:
    """그 세계관의 업적마다 받은 사람의 수. 아무도 받지 않은 업적은 없다. id 의 차례다."""
    query = (
        select(AchievementRecord.achievement_id, func.count())
        .where(AchievementRecord.world_source == world_source)
        .group_by(AchievementRecord.achievement_id)
        .order_by(AchievementRecord.achievement_id)
    )
    return [(achievement_id, count) for achievement_id, count in await session.execute(query)]
