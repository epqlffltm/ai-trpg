# asset-server/app/rankings/repository.py

"""
랭킹을 DB 에서 읽는다(#985). SQL 은 이 파일에만 있다.

공개 목록의 조건(characters.listed, worlds.listed)에 맞는 작품만 쌓아 둔 시작 수와 잇는다.
최근의 수가 0 인 것은 빠진다. 같으면 모든 수, 그것도 같으면 최근에 게시한 것이 먼저다.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters import repository as characters
from app.characters.models import Character, CharacterVersion
from app.exclusions import NO_EXCLUSIONS, Exclusions, not_excluded
from app.ratings import Rating
from app.stats.models import WorkKind, WorkStarts
from app.worlds import repository as worlds
from app.worlds.models import World, WorldVersion


async def ranked_characters(
    session: AsyncSession,
    ratings: Sequence[Rating],
    orientation_tag: str | None,
    limit: int,
    excluded: Exclusions = NO_EXCLUSIONS,
) -> list[tuple[Character, CharacterVersion, int]]:
    """볼 수 있는 캐릭터의 랭킹. 캐릭터, 마지막 판, 최근의 수다. 막은 제작자와 태그(#988)의 것은 뺀다."""
    condition = characters.listed(ratings) & (WorkStarts.recent > 0)
    condition = condition & not_excluded(excluded, Character.owner_id, CharacterVersion.document)
    if orientation_tag is not None:
        condition = condition & CharacterVersion.document['tags'].contains([orientation_tag])
    query = (
        select(Character, CharacterVersion, WorkStarts.recent)
        .join(CharacterVersion, characters.latest_join())
        .join(WorkStarts, (WorkStarts.kind == WorkKind.CHARACTER) & (WorkStarts.work_id == Character.id))
        .where(condition)
        .order_by(WorkStarts.recent.desc(), WorkStarts.total.desc(), Character.published_at.desc(), Character.id)
        .limit(limit)
    )
    rows = await session.execute(query)
    return [(character, version, recent) for character, version, recent in rows.all()]


async def ranked_worlds(
    session: AsyncSession,
    ratings: Sequence[Rating],
    orientation_tag: str | None,
    limit: int,
    excluded: Exclusions = NO_EXCLUSIONS,
) -> list[tuple[World, WorldVersion, int]]:
    """볼 수 있는 세계관의 랭킹. 세계관, 마지막 판, 최근의 수다. 막은 제작자와 태그(#988)의 것은 뺀다."""
    condition = worlds.listed(ratings) & (WorkStarts.recent > 0)
    condition = condition & not_excluded(excluded, World.owner_id, WorldVersion.document)
    if orientation_tag is not None:
        condition = condition & WorldVersion.document['tags'].contains([orientation_tag])
    query = (
        select(World, WorldVersion, WorkStarts.recent)
        .join(WorldVersion, worlds.latest_join())
        .join(WorkStarts, (WorkStarts.kind == WorkKind.WORLD) & (WorkStarts.work_id == World.id))
        .where(condition)
        .order_by(WorkStarts.recent.desc(), WorkStarts.total.desc(), World.published_at.desc(), World.id)
        .limit(limit)
    )
    rows = await session.execute(query)
    return [(world, version, recent) for world, version, recent in rows.all()]


async def refreshed_at(session: AsyncSession, kind: WorkKind) -> datetime | None:
    """그 종류의 수를 받아 온 시각. 받은 것이 없으면 None 이다."""
    return await session.scalar(select(func.max(WorkStarts.refreshed_at)).where(WorkStarts.kind == kind))
