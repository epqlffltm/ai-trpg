# asset-server/app/operators/repository.py

"""
운영자의 조치를 위한 DB 읽기와 쓰기. 커밋하지 않는다.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character
from app.operators.models import OperatorAction


def add_action(session: AsyncSession, action: OperatorAction) -> None:
    """감사 기록 한 줄을 세션에 올린다."""
    session.add(action)


async def lock_character(session: AsyncSession, character_id: uuid.UUID) -> Character | None:
    """캐릭터 하나(주인을 가리지 않는다)를 잠가 읽는다. 없으면 None. 숨기기와 처리를 차례로 하게 한다."""
    return await session.scalar(select(Character).where(Character.id == character_id).with_for_update())
