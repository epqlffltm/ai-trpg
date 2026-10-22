# chat-server/app/memory/repository.py

"""
기억 메모를 읽고 적는다.
"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.memory.models import MemoryNote


async def list_notes(session: AsyncSession, conversation_id: uuid.UUID) -> list[MemoryNote]:
    """대화의 메모들. 먼저 쓴 것부터."""
    query = (
        select(MemoryNote)
        .where(MemoryNote.conversation_id == conversation_id)
        .order_by(MemoryNote.created_at, MemoryNote.id)
    )
    return list(await session.scalars(query))


async def count_notes(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    """대화의 메모 수."""
    query = select(func.count()).select_from(MemoryNote).where(MemoryNote.conversation_id == conversation_id)
    return await session.scalar(query)


async def find_note(session: AsyncSession, conversation_id: uuid.UUID, note_id: uuid.UUID) -> MemoryNote | None:
    """그 대화의 메모 하나. 다른 대화의 것이면 None."""
    note = await session.get(MemoryNote, note_id)
    return note if note is not None and note.conversation_id == conversation_id else None


def add_note(session: AsyncSession, note: MemoryNote) -> None:
    """새 메모를 세션에 올린다."""
    session.add(note)


async def delete_note(session: AsyncSession, note_id: uuid.UUID) -> None:
    """메모 하나를 지운다."""
    await session.execute(delete(MemoryNote).where(MemoryNote.id == note_id))


async def lock_conversation(session: AsyncSession, conversation_id: uuid.UUID) -> None:
    """대화의 행을 잠근다(트랜잭션이 끝날 때까지). 메모를 동시에 더해도 수의 상한을 넘지 않게 한다."""
    await session.execute(select(Conversation.id).where(Conversation.id == conversation_id).with_for_update())
