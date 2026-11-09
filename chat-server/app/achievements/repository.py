# chat-server/app/achievements/repository.py

"""
받은 업적과 대화한 사람의 기록을 읽고 적는다(app/achievements/models.py). 쿼리만 한다. 저장(commit)은 부르는 쪽이 한다.

같은 사람이 같은 업적을 다시 받거나 같은 캐릭터와 다시 대화해도 줄은 하나다(기본 키).
그래서 쓰기는 모두 "있으면 그대로"(ON CONFLICT DO NOTHING)다. 두 대화가 함께 줘도 막히지 않는다.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.achievements.models import AchievementRecord, CharacterPlayer
from app.assets.schemas import AchievementDocument


async def mark_played(session: AsyncSession, owner_id: uuid.UUID, character_source: uuid.UUID, now: datetime) -> None:
    """그 사람이 그 캐릭터와 대화했다고 적는다. 이미 적혔으면 그대로 둔다(처음 대화한 때를 바꾸지 않는다)."""
    statement = (
        insert(CharacterPlayer)
        .values(owner_id=owner_id, character_source=character_source, first_played_at=now)
        .on_conflict_do_nothing(index_elements=['owner_id', 'character_source'])
    )
    await session.execute(statement)


async def achievement_ids_of(session: AsyncSession, owner_id: uuid.UUID, character_source: uuid.UUID) -> frozenset[str]:
    """그 사람이 그 캐릭터에서 받은 업적의 id 들."""
    query = select(AchievementRecord.achievement_id).where(
        AchievementRecord.owner_id == owner_id, AchievementRecord.character_source == character_source
    )
    return frozenset(await session.scalars(query))


async def add_achievements(
    session: AsyncSession,
    owner_id: uuid.UUID,
    character_source: uuid.UUID,
    achievements: Sequence[AchievementDocument],
    conversation_id: uuid.UUID | None,
    now: datetime,
) -> frozenset[str]:
    """
    받은 업적들을 적고, 이번에 새로 적힌 것의 id 를 돌려준다.
    이미 받은 것은 그대로 둔다(처음 받은 때, 이름, 대화를 바꾸지 않는다).
    두 대화가 함께 줘도 하나만 적히고 하나만 알린다.
    """
    if not achievements:
        return frozenset()
    rows = [
        {
            'owner_id': owner_id,
            'character_source': character_source,
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
        .on_conflict_do_nothing(index_elements=['owner_id', 'character_source', 'achievement_id'])
        .returning(AchievementRecord.achievement_id)
    )
    return frozenset(await session.scalars(statement))


async def achievements_of(
    session: AsyncSession, owner_id: uuid.UUID, character_source: uuid.UUID
) -> list[AchievementRecord]:
    """그 사람이 그 캐릭터에서 받은 업적들. 받은 차례다."""
    query = (
        select(AchievementRecord)
        .where(AchievementRecord.owner_id == owner_id, AchievementRecord.character_source == character_source)
        .order_by(AchievementRecord.earned_at, AchievementRecord.achievement_id)
    )
    return list(await session.scalars(query))


async def count_players(session: AsyncSession, character_source: uuid.UUID) -> int:
    """그 캐릭터와 대화한 사람의 수."""
    query = (
        select(func.count()).select_from(CharacterPlayer).where(CharacterPlayer.character_source == character_source)
    )
    return await session.scalar(query) or 0


async def count_earned(session: AsyncSession, character_source: uuid.UUID) -> list[tuple[str, int]]:
    """그 캐릭터의 업적마다 받은 사람의 수. 아무도 받지 않은 업적은 없다. id 의 차례다."""
    query = (
        select(AchievementRecord.achievement_id, func.count())
        .where(AchievementRecord.character_source == character_source)
        .group_by(AchievementRecord.achievement_id)
        .order_by(AchievementRecord.achievement_id)
    )
    return [(achievement_id, count) for achievement_id, count in await session.execute(query)]


async def delete_all_of(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """그 사람의 받은 업적과 대화한 기록을 모두 지운다(탈퇴). 달성률에서 빠진다."""
    await session.execute(delete(AchievementRecord).where(AchievementRecord.owner_id == owner_id))
    await session.execute(delete(CharacterPlayer).where(CharacterPlayer.owner_id == owner_id))
