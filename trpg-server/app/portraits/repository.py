# trpg-server/app/portraits/repository.py

"""캐릭터 그림의 기록을 넣고 찾는다. 저장(commit)은 서비스가 한다."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.portraits.models import Portrait


async def count_owned(session: AsyncSession, owner_id: uuid.UUID) -> int:
    """이 사람이 올린 그림의 수."""
    total = await session.scalar(select(func.count()).select_from(Portrait).where(Portrait.owner_id == owner_id))
    return total or 0


def add(session: AsyncSession, image_id: uuid.UUID, owner_id: uuid.UUID) -> Portrait:
    """기록 하나를 넣는다."""
    portrait = Portrait(id=image_id, owner_id=owner_id)
    session.add(portrait)
    return portrait


async def list_owned(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[Portrait], int]:
    """이 사람이 올린 그림들의 한 쪽과 전체 개수. 최근에 올린 것부터다."""
    query = select(Portrait).where(Portrait.owner_id == owner_id)
    page = query.order_by(Portrait.created_at.desc(), Portrait.id.desc()).limit(limit).offset(offset)
    rows = await session.scalars(page)
    return list(rows), await count_owned(session, owner_id)


async def owned_ids(session: AsyncSession, owner_id: uuid.UUID, image_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """그 id 들 가운데 이 사람이 올린 그림의 id 들."""
    if not image_ids:
        return set()
    query = select(Portrait.id).where(Portrait.owner_id == owner_id, Portrait.id.in_(image_ids))
    return set(await session.scalars(query))


async def find_owned(session: AsyncSession, owner_id: uuid.UUID, image_id: uuid.UUID) -> Portrait | None:
    """이 사람이 올린 그림 하나. 남의 것이나 없는 것이면 None."""
    query = select(Portrait).where(Portrait.id == image_id, Portrait.owner_id == owner_id)
    return await session.scalar(query)
