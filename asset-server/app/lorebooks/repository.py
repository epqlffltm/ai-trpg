# asset-server/app/lorebooks/repository.py

"""
로어북과 그 판을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

초안을 다루는 함수는 주인의 ID 를 받는다. 로어북의 ID 만으로 남의 초안을 건드리는 길이 없다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete as delete_rows
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lorebooks.models import Lorebook, LorebookVersion


def add(session: AsyncSession, row: Lorebook | LorebookVersion) -> None:
    """새 로어북이나 판을 세션에 올린다."""
    session.add(row)


async def find_owned(
    session: AsyncSession, owner_id: uuid.UUID, lorebook_id: uuid.UUID, for_update: bool = False
) -> Lorebook | None:
    """이 사람의 로어북 하나. 없거나 남의 것이면 None. for_update 면 행을 잠근다(동시 게시의 번호)."""
    query = select(Lorebook).where(Lorebook.id == lorebook_id, Lorebook.owner_id == owner_id)
    if for_update:
        query = query.with_for_update()
    return await session.scalar(query)


async def list_owned(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[Lorebook], int]:
    """이 사람의 로어북의 한 쪽(최근에 고친 것부터)과 전체 개수."""
    condition = Lorebook.owner_id == owner_id
    query = (
        select(Lorebook).where(condition).order_by(Lorebook.updated_at.desc(), Lorebook.id).limit(limit).offset(offset)
    )
    total = await session.scalar(select(func.count()).select_from(Lorebook).where(condition))
    return list(await session.scalars(query)), total or 0


async def owned_ids(session: AsyncSession, owner_id: uuid.UUID, lorebook_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
    """그 가운데 이 사람의 로어북인 것들의 id."""
    query = select(Lorebook.id).where(Lorebook.owner_id == owner_id, Lorebook.id.in_(lorebook_ids))
    return set(await session.scalars(query))


async def delete(session: AsyncSession, lorebook: Lorebook) -> None:
    """로어북의 행을 지운다. 판도 함께 지워진다(외래 키의 CASCADE)."""
    await session.delete(lorebook)


async def delete_owned(session: AsyncSession, owner_id: uuid.UUID) -> int:
    """이 사람의 로어북을 모두 지운다(탈퇴). 판도 함께 지워진다. 지운 수를 돌려준다."""
    result = await session.execute(delete_rows(Lorebook).where(Lorebook.owner_id == owner_id))
    return result.rowcount


async def list_versions(session: AsyncSession, lorebook_id: uuid.UUID) -> list[LorebookVersion]:
    """로어북의 판들. 최근 것부터다."""
    query = (
        select(LorebookVersion)
        .where(LorebookVersion.lorebook_id == lorebook_id)
        .order_by(LorebookVersion.number.desc())
    )
    return list(await session.scalars(query))


async def find_version(session: AsyncSession, lorebook_id: uuid.UUID, number: int) -> LorebookVersion | None:
    """로어북의 판 하나. 없으면 None."""
    query = select(LorebookVersion).where(LorebookVersion.lorebook_id == lorebook_id, LorebookVersion.number == number)
    return await session.scalar(query)


async def latest_owned(
    session: AsyncSession, owner_id: uuid.UUID, lorebook_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[Lorebook, LorebookVersion | None]]:
    """
    그 가운데 이 사람의 로어북과 그 마지막 판(게시한 적이 없으면 None). 남의 것이나 없는 것은 빠진다.
    캐릭터를 게시할 때 판에 복사할 것을 찾는다. 한 번의 쿼리다.
    """
    join = (LorebookVersion.lorebook_id == Lorebook.id) & (LorebookVersion.number == Lorebook.latest_version)
    query = (
        select(Lorebook, LorebookVersion)
        .outerjoin(LorebookVersion, join)
        .where(Lorebook.owner_id == owner_id, Lorebook.id.in_(lorebook_ids))
    )
    rows = await session.execute(query)
    return {lorebook.id: (lorebook, version) for lorebook, version in rows.all()}
