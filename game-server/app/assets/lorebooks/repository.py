# game-server/app/assets/lorebooks/repository.py

"""
로어북의 항목을 DB 에서 읽고 쓴다. 커밋하지 않는다.

로어북 자신은 공통 저장소(app/assets/repository.py)가 다룬다.
여기의 함수는 "누구의 것인가"를 묻지 않는다. 로어북이 그 사람의 것인지는 서비스가 먼저 확인한다.
대신 모든 함수가 로어북의 ID 를 받는다. 항목의 ID 만으로 남의 로어북의 항목을 건드리는 길이 없다.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import LoreEntry


def add_entry(session: AsyncSession, entry: LoreEntry) -> None:
    """새 항목을 세션에 올린다."""
    session.add(entry)


async def find_entry(session: AsyncSession, lorebook_id: uuid.UUID, entry_id: uuid.UUID) -> LoreEntry | None:
    """로어북의 항목 하나를 찾는다. 없거나 다른 로어북의 항목이면 None."""
    query = select(LoreEntry).where(LoreEntry.id == entry_id, LoreEntry.lorebook_id == lorebook_id)
    return await session.scalar(query)


async def list_entries(session: AsyncSession, lorebook_id: uuid.UUID) -> list[LoreEntry]:
    """로어북의 항목을 만든 순서대로 전부 돌려준다. 개수에 상한이 있어서 쪽을 나누지 않는다."""
    query = select(LoreEntry).where(LoreEntry.lorebook_id == lorebook_id).order_by(LoreEntry.created_at, LoreEntry.id)
    result = await session.scalars(query)
    return list(result)


async def count_entries(session: AsyncSession, lorebook_id: uuid.UUID) -> int:
    """로어북의 항목이 몇 개인지 센다."""
    query = select(func.count()).select_from(LoreEntry).where(LoreEntry.lorebook_id == lorebook_id)
    return await session.scalar(query) or 0


async def delete_entry(session: AsyncSession, entry: LoreEntry) -> None:
    """항목의 행을 지운다."""
    await session.delete(entry)
