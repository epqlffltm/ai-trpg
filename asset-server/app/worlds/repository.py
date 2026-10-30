# asset-server/app/worlds/repository.py

"""
세계관과 그 판을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

초안을 다루는 함수는 주인의 ID 를 받는다. 세계관의 ID 만으로 남의 초안을 건드리는 길이 없다(캐릭터와 같다).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete as delete_rows
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Visibility
from app.ratings import Rating
from app.worlds.models import World, WorldVersion


def add(session: AsyncSession, row: World | WorldVersion) -> None:
    """새 세계관이나 판을 세션에 올린다."""
    session.add(row)


async def find_owned(
    session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID, for_update: bool = False
) -> World | None:
    """
    이 사람의 세계관 하나. 없거나 남의 것이면 None.

    for_update 면 행을 잠근다. 동시에 게시하는 두 요청이 같은 번호를 쓰지 않게 한다.
    """
    query = select(World).where(World.id == world_id, World.owner_id == owner_id)
    if for_update:
        query = query.with_for_update()
    return await session.scalar(query)


async def list_owned(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[World], int]:
    """이 사람의 세계관의 한 쪽(최근에 고친 것부터)과 전체 개수."""
    condition = World.owner_id == owner_id
    query = select(World).where(condition).order_by(World.updated_at.desc(), World.id).limit(limit).offset(offset)
    total = await session.scalar(select(func.count()).select_from(World).where(condition))
    return list(await session.scalars(query)), total or 0


async def delete(session: AsyncSession, world: World) -> None:
    """세계관의 행을 지운다. 판도 함께 지워진다(외래 키의 CASCADE)."""
    await session.delete(world)


async def delete_private_owned(session: AsyncSession, owner_id: uuid.UUID) -> int:
    """
    이 사람의 비공개 세계관을 모두 지운다(탈퇴). 판도 함께 지워진다. 지운 수를 돌려준다.
    공개 세계관은 남긴다. 남이 쓰는 것이다(캐릭터와 같다).
    """
    condition = (World.owner_id == owner_id) & (World.visibility == Visibility.PRIVATE)
    result = await session.execute(delete_rows(World).where(condition))
    return result.rowcount


async def list_versions(session: AsyncSession, world_id: uuid.UUID) -> list[WorldVersion]:
    """세계관의 판들. 최근 것부터다."""
    query = select(WorldVersion).where(WorldVersion.world_id == world_id).order_by(WorldVersion.number.desc())
    return list(await session.scalars(query))


async def find_version(session: AsyncSession, world_id: uuid.UUID, number: int) -> WorldVersion | None:
    """세계관의 판 하나. 없으면 None."""
    query = select(WorldVersion).where(WorldVersion.world_id == world_id, WorldVersion.number == number)
    return await session.scalar(query)


def latest_join():
    """세계관과 그 마지막 판을 잇는 조건. 게시한 적이 없는 세계관은 이어지지 않는다."""
    return (WorldVersion.world_id == World.id) & (WorldVersion.number == World.latest_version)


async def find_latest(session: AsyncSession, world_id: uuid.UUID) -> tuple[World, WorldVersion] | None:
    """
    세계관 하나와 그 마지막 판. 주인과 공개 범위를 가리지 않는다. 없거나 게시한 적이 없으면 None.
    story 서버에 판을 내줄 때 쓴다. 쓸 수 있는 사람인지는 서비스가 본다.
    """
    query = select(World, WorldVersion).join(WorldVersion, latest_join()).where(World.id == world_id)
    row = (await session.execute(query)).first()
    return None if row is None else (row[0], row[1])


def listed(ratings: Sequence[Rating]):
    """
    공개 목록에 나오는 조건. 공개이고, 운영자가 숨기지 않았고, 마지막 판이 볼 수 있는 등급이다
    (캐릭터의 공개 목록과 같다).
    등급은 판의 것으로 거른다. 초안의 등급을 바꿔도 다음 판까지는 게시한 판이 나간다.
    """
    return (
        (World.visibility == Visibility.PUBLIC)
        & World.hidden_at.is_(None)
        & WorldVersion.rating.in_([rating.value for rating in ratings])
    )


async def list_public(
    session: AsyncSession, ratings: Sequence[Rating], limit: int, offset: int
) -> tuple[list[tuple[World, WorldVersion]], int]:
    """공개 목록의 한 쪽(최근에 게시한 것부터)과 전체 개수. 세계관마다 마지막 판과 함께다."""
    condition = listed(ratings)
    query = (
        select(World, WorldVersion)
        .join(WorldVersion, latest_join())
        .where(condition)
        .order_by(World.published_at.desc(), World.id)
        .limit(limit)
        .offset(offset)
    )
    count = select(func.count()).select_from(World).join(WorldVersion, latest_join()).where(condition)
    rows = await session.execute(query)
    return [(world, version) for world, version in rows.all()], await session.scalar(count) or 0


async def find_public(
    session: AsyncSession, world_id: uuid.UUID, ratings: Sequence[Rating]
) -> tuple[World, WorldVersion] | None:
    """공개 세계관 하나와 그 마지막 판. 공개가 아니거나, 숨겼거나, 판이 없거나, 볼 수 없는 등급이면 None."""
    query = select(World, WorldVersion).join(WorldVersion, latest_join()).where(World.id == world_id, listed(ratings))
    row = (await session.execute(query)).first()
    return None if row is None else (row[0], row[1])
