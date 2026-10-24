# story-server/app/conversations/repository.py

"""
세션과 판의 사본을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

세션을 읽는 함수는 주인의 ID 와 볼 수 있는 등급을 받는다. 세션의 ID 만으로 남의 세션을 읽는 길이 없다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ImportedWorld
from app.ratings import Rating

# 세션 하나를 읽을 때 함께 오는 것: 세션과 판의 사본
ConversationRow = tuple[Conversation, ImportedWorld]


def add(session: AsyncSession, row: Conversation) -> None:
    """새 행을 세션에 올린다."""
    session.add(row)


async def keep_world(session: AsyncSession, world: ImportedWorld) -> ImportedWorld:
    """
    판의 사본을 둔다. 그 사람이 같은 판을 이미 가져왔으면 있는 것을 돌려준다.

    두 요청이 같은 판을 동시에 가져와도 하나만 남는다. 넣다가 겹치면 넣지 않고(ON CONFLICT DO NOTHING) 있는 것을 읽는다.
    """
    values = {
        'id': world.id,
        'owner_id': world.owner_id,
        'source_id': world.source_id,
        'version': world.version,
        'name': world.name,
        'rating': world.rating,
        'document': world.document,
    }
    statement = (
        insert(ImportedWorld).values(values).on_conflict_do_nothing(index_elements=['owner_id', 'source_id', 'version'])
    )
    await session.execute(statement)
    query = select(ImportedWorld).where(
        ImportedWorld.owner_id == world.owner_id,
        ImportedWorld.source_id == world.source_id,
        ImportedWorld.version == world.version,
    )
    return (await session.scalars(query)).one()


def visible(owner_id: uuid.UUID, ratings: Sequence[Rating]) -> Select:
    """이 사람의 세션 가운데 볼 수 있는 등급의 것. 세션과 판의 사본을 함께 고른다."""
    return (
        select(Conversation, ImportedWorld)
        .join(ImportedWorld, ImportedWorld.id == Conversation.world_id)
        .where(
            Conversation.owner_id == owner_id,
            ImportedWorld.rating.in_([rating.value for rating in ratings]),
        )
    )


async def list_visible(
    session: AsyncSession,
    owner_id: uuid.UUID,
    ratings: Sequence[Rating],
    source_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[ConversationRow], int]:
    """세션의 한 쪽(최근의 것부터)과 전체 개수. source_id 를 주면 그 세계관(asset 서버의 id)의 세션만이다."""
    query = visible(owner_id, ratings)
    if source_id is not None:
        query = query.where(ImportedWorld.source_id == source_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    page = query.order_by(Conversation.updated_at.desc(), Conversation.id).limit(limit).offset(offset)
    rows = await session.execute(page)
    return [(conversation, world) for conversation, world in rows.all()], total or 0


async def find_visible(
    session: AsyncSession, owner_id: uuid.UUID, ratings: Sequence[Rating], conversation_id: uuid.UUID
) -> ConversationRow | None:
    """이 사람의 세션 하나와 판의 사본. 없거나, 남의 것이거나, 볼 수 없는 등급이면 None."""
    row = (await session.execute(visible(owner_id, ratings).where(Conversation.id == conversation_id))).first()
    return None if row is None else (row[0], row[1])
