# asset-server/app/worlds/repository.py

"""
세계관과 그 판을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

초안을 다루는 함수는 주인의 ID 를 받는다. 세계관의 ID 만으로 남의 초안을 건드리는 길이 없다(캐릭터와 같다).
"""

import uuid

from sqlalchemy import delete as delete_rows
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Visibility
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
