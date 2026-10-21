# asset-server/app/characters/repository.py

"""
캐릭터와 그 판을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

초안을 다루는 함수는 주인의 ID 를 받는다. 캐릭터의 ID 만으로 남의 초안을 건드리는 길이 없다.
공개 목록의 함수는 공개이고 게시한 판이 있는 것만 읽는다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character, CharacterVersion, Visibility
from app.ratings import Rating


def add(session: AsyncSession, row: Character | CharacterVersion) -> None:
    """새 캐릭터나 판을 세션에 올린다."""
    session.add(row)


async def find_owned(
    session: AsyncSession, owner_id: uuid.UUID, character_id: uuid.UUID, for_update: bool = False
) -> Character | None:
    """
    이 사람의 캐릭터 하나. 없거나 남의 것이면 None.

    for_update 면 행을 잠근다. 동시에 게시하는 두 요청이 같은 번호를 쓰지 않게 한다.
    """
    query = select(Character).where(Character.id == character_id, Character.owner_id == owner_id)
    if for_update:
        query = query.with_for_update()
    return await session.scalar(query)


async def list_owned(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Character], int]:
    """이 사람의 캐릭터의 한 쪽(최근에 고친 것부터)과 전체 개수."""
    condition = Character.owner_id == owner_id
    query = (
        select(Character)
        .where(condition)
        .order_by(Character.updated_at.desc(), Character.id)
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(select(func.count()).select_from(Character).where(condition))
    return list(await session.scalars(query)), total or 0


async def delete(session: AsyncSession, character: Character) -> None:
    """캐릭터의 행을 지운다. 판도 함께 지워진다(외래 키의 CASCADE)."""
    await session.delete(character)


async def list_versions(session: AsyncSession, character_id: uuid.UUID) -> list[CharacterVersion]:
    """캐릭터의 판들. 최근 것부터다."""
    query = (
        select(CharacterVersion)
        .where(CharacterVersion.character_id == character_id)
        .order_by(CharacterVersion.number.desc())
    )
    return list(await session.scalars(query))


async def find_version(session: AsyncSession, character_id: uuid.UUID, number: int) -> CharacterVersion | None:
    """캐릭터의 판 하나. 없으면 None."""
    query = select(CharacterVersion).where(
        CharacterVersion.character_id == character_id, CharacterVersion.number == number
    )
    return await session.scalar(query)


def listed(ratings: Sequence[Rating]):
    """
    공개 목록에 나오는 조건. 공개이고, 마지막 판이 볼 수 있는 등급이다.

    등급은 판의 것으로 거른다. 초안의 등급을 바꿔도 다음 판까지는 게시한 판이 나간다. 그 판의 등급이 맞아야 한다.
    """
    return (Character.visibility == Visibility.PUBLIC) & CharacterVersion.rating.in_(
        [rating.value for rating in ratings]
    )


def latest_join():
    """캐릭터와 그 마지막 판을 잇는 조건. 게시한 적이 없는 캐릭터는 이어지지 않는다."""
    return (CharacterVersion.character_id == Character.id) & (CharacterVersion.number == Character.latest_version)


async def list_public(
    session: AsyncSession, ratings: Sequence[Rating], limit: int, offset: int
) -> tuple[list[tuple[Character, CharacterVersion]], int]:
    """공개 목록의 한 쪽(최근에 게시한 것부터)과 전체 개수. 캐릭터마다 마지막 판과 함께다."""
    condition = listed(ratings)
    query = (
        select(Character, CharacterVersion)
        .join(CharacterVersion, latest_join())
        .where(condition)
        .order_by(Character.published_at.desc(), Character.id)
        .limit(limit)
        .offset(offset)
    )
    count = select(func.count()).select_from(Character).join(CharacterVersion, latest_join()).where(condition)
    rows = await session.execute(query)
    return [(character, version) for character, version in rows.all()], await session.scalar(count) or 0


async def find_public(
    session: AsyncSession, character_id: uuid.UUID, ratings: Sequence[Rating]
) -> tuple[Character, CharacterVersion] | None:
    """공개 캐릭터 하나와 그 마지막 판. 공개가 아니거나, 판이 없거나, 볼 수 없는 등급이면 None."""
    query = (
        select(Character, CharacterVersion)
        .join(CharacterVersion, latest_join())
        .where(Character.id == character_id, listed(ratings))
    )
    row = (await session.execute(query)).first()
    return None if row is None else (row[0], row[1])
