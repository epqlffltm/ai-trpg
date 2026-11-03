# asset-server/app/shortcuts/repository.py

"""
내 단축어의 쿼리. 커밋하지 않는다.
"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.shortcuts.models import UserShortcuts


async def items_of(session: AsyncSession, owner_id: uuid.UUID) -> list[dict]:
    """그 사람의 단축어들. 적지 않았으면 빈 목록이다."""
    found = await session.scalar(select(UserShortcuts.items).where(UserShortcuts.owner_id == owner_id))
    return list(found or [])


async def replace(session: AsyncSession, owner_id: uuid.UUID, items: list[dict]) -> None:
    """그 사람의 단축어를 통째로 바꾼다. 줄이 없으면 만든다."""
    statement = insert(UserShortcuts).values(owner_id=owner_id, items=items)
    await session.execute(
        statement.on_conflict_do_update(index_elements=['owner_id'], set_={'items': items, 'updated_at': func.now()})
    )


async def delete_owned(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """그 사람의 단축어를 지운다(탈퇴)."""
    await session.execute(delete(UserShortcuts).where(UserShortcuts.owner_id == owner_id))
