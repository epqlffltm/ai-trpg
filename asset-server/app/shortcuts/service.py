# asset-server/app/shortcuts/service.py

"""
내 단축어를 읽고 통째로 바꾼다(#981). 자기 것만 다룬다. 모양과 상한은 받을 때(schemas) 이미 봤다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.shortcuts import repository
from app.shortcuts.schemas import Shortcut, shortcut_rows


async def list_shortcuts(session: AsyncSession, owner_id: uuid.UUID) -> list[Shortcut]:
    """그 사람의 단축어들(적은 차례)."""
    return [Shortcut.model_validate(item) for item in await repository.items_of(session, owner_id)]


async def replace_shortcuts(session: AsyncSession, owner_id: uuid.UUID, shortcuts: list[Shortcut]) -> list[Shortcut]:
    """그 사람의 단축어를 통째로 바꾸고 바꾼 것을 돌려준다. 빈 목록이면 모두 지운 것이다."""
    await repository.replace(session, owner_id, shortcut_rows(shortcuts))
    await session.commit()
    return list(shortcuts)
