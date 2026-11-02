# story-server/app/bookmarks/repository.py

"""
책갈피를 읽고 적는 쿼리. 커밋하지 않는다.
"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookmarks.models import Bookmark
from app.conversations.models import Conversation, Message


async def list_with_messages(session: AsyncSession, conversation_id: uuid.UUID) -> list[tuple[Bookmark, Message]]:
    """세션의 책갈피와 그 말. 나중에 단 것부터."""
    query = (
        select(Bookmark, Message)
        .join(Message, Message.id == Bookmark.message_id)
        .where(Bookmark.conversation_id == conversation_id)
        .order_by(Bookmark.created_at.desc(), Bookmark.message_id)
    )
    return [(bookmark, message) for bookmark, message in (await session.execute(query)).all()]


async def find(session: AsyncSession, message_id: uuid.UUID) -> Bookmark | None:
    """그 말의 책갈피. 없으면 None."""
    return await session.get(Bookmark, message_id, populate_existing=True)


async def count(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    """세션의 책갈피 수."""
    query = select(func.count()).select_from(Bookmark).where(Bookmark.conversation_id == conversation_id)
    return await session.scalar(query)


async def lock_conversation(session: AsyncSession, conversation_id: uuid.UUID) -> None:
    """세션의 행을 잠근다(트랜잭션이 끝날 때까지). 책갈피를 동시에 달아도 수의 상한을 넘지 않게 한다."""
    await session.execute(select(Conversation.id).where(Conversation.id == conversation_id).with_for_update())


async def put(session: AsyncSession, conversation_id: uuid.UUID, message_id: uuid.UUID, note: str | None) -> None:
    """책갈피를 단다. 이미 있으면 메모만 바꾼다."""
    statement = insert(Bookmark).values(message_id=message_id, conversation_id=conversation_id, note=note)
    await session.execute(
        statement.on_conflict_do_update(index_elements=['message_id'], set_={'note': note, 'updated_at': func.now()})
    )


async def remove(session: AsyncSession, message_id: uuid.UUID) -> None:
    """그 말의 책갈피를 뗀다. 없으면 아무것도 하지 않는다."""
    await session.execute(delete(Bookmark).where(Bookmark.message_id == message_id))


async def remove_all(session: AsyncSession, conversation_id: uuid.UUID) -> None:
    """세션의 책갈피를 모두 뗀다(세션을 지울 때)."""
    await session.execute(delete(Bookmark).where(Bookmark.conversation_id == conversation_id))
