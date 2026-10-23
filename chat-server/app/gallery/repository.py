# chat-server/app/gallery/repository.py

"""
연 이벤트 씬의 기록을 읽고 적는다. 저장(commit)은 부르는 쪽이 한다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.gallery.models import SceneUnlock


async def add_unlocks(
    session: AsyncSession, owner_id: uuid.UUID, character_source: uuid.UUID, scene_ids: Sequence[str]
) -> None:
    """연 것으로 적는다. 이미 연 것은 그대로 둔다(처음 연 시각이 남는다)."""
    if not scene_ids:
        return
    rows = [
        {'owner_id': owner_id, 'character_source': character_source, 'scene_id': scene_id} for scene_id in scene_ids
    ]
    await session.execute(insert(SceneUnlock).values(rows).on_conflict_do_nothing())


def mine(owner_id: uuid.UUID, character_source: uuid.UUID | None):
    """내가 연 것의 조건. character_source 를 주면 그 캐릭터의 것만이다."""
    conditions = [SceneUnlock.owner_id == owner_id]
    if character_source is not None:
        conditions.append(SceneUnlock.character_source == character_source)
    return conditions


async def list_unlocks(
    session: AsyncSession, owner_id: uuid.UUID, character_source: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[SceneUnlock], int]:
    """내가 연 것들(최근에 연 것부터)과 전체 개수."""
    conditions = mine(owner_id, character_source)
    query = (
        select(SceneUnlock)
        .where(*conditions)
        .order_by(SceneUnlock.unlocked_at.desc(), SceneUnlock.scene_id)
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.scalars(query)).all())
    total = await session.scalar(select(func.count()).select_from(SceneUnlock).where(*conditions))
    return rows, total or 0


async def delete_owned(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """그 사람의 기록을 모두 지운다(탈퇴)."""
    await session.execute(delete(SceneUnlock).where(SceneUnlock.owner_id == owner_id))
