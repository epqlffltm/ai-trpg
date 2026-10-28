# story-server/app/memory/repository.py

"""
기억 메모와 굴리는 요약을 읽고 적는다. 커밋하지 않는다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.memory.models import MemoryNote, Summary


async def list_notes(session: AsyncSession, conversation_id: uuid.UUID) -> list[MemoryNote]:
    """세션의 메모들. 먼저 쓴 것부터."""
    query = (
        select(MemoryNote)
        .where(MemoryNote.conversation_id == conversation_id)
        .order_by(MemoryNote.created_at, MemoryNote.id)
    )
    return list(await session.scalars(query))


async def count_notes(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    """세션의 메모 수."""
    query = select(func.count()).select_from(MemoryNote).where(MemoryNote.conversation_id == conversation_id)
    return await session.scalar(query)


async def find_note(session: AsyncSession, conversation_id: uuid.UUID, note_id: uuid.UUID) -> MemoryNote | None:
    """그 세션의 메모 하나. 다른 세션의 것이면 None."""
    note = await session.get(MemoryNote, note_id)
    return note if note is not None and note.conversation_id == conversation_id else None


def add_note(session: AsyncSession, note: MemoryNote) -> None:
    """새 메모를 세션에 올린다."""
    session.add(note)


async def delete_note(session: AsyncSession, note_id: uuid.UUID) -> None:
    """메모 하나를 지운다."""
    await session.execute(delete(MemoryNote).where(MemoryNote.id == note_id))


async def lock_conversation(session: AsyncSession, conversation_id: uuid.UUID) -> None:
    """세션의 행을 잠근다(트랜잭션이 끝날 때까지). 메모를 동시에 더해도 수의 상한을 넘지 않게 한다."""
    await session.execute(select(Conversation.id).where(Conversation.id == conversation_id).with_for_update())


async def summaries_on(session: AsyncSession, message_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    """그 말들 가운데 요약이 붙은 것의 요약의 글. 한 번의 쿼리다."""
    if not message_ids:
        return {}
    query = select(Summary.message_id, Summary.text).where(Summary.message_id.in_(message_ids))
    return {message_id: text for message_id, text in await session.execute(query)}


async def latest_summary_row(session: AsyncSession, message_ids: Sequence[uuid.UUID]) -> Summary | None:
    """그 말들(가지의 차례) 가운데 요약이 붙은 가장 뒤의 말의 요약. 없으면 None."""
    if not message_ids:
        return None
    rows = {
        row.message_id: row for row in await session.scalars(select(Summary).where(Summary.message_id.in_(message_ids)))
    }
    return next((rows[message_id] for message_id in reversed(message_ids) if message_id in rows), None)


async def add_summary(session: AsyncSession, summary: Summary) -> None:
    """요약을 적는다. 같은 말의 요약이 이미 있으면(다른 작업이 먼저 썼다) 두지 않는다."""
    values = {
        column.key: getattr(summary, column.key) for column in Summary.__table__.columns if column.key != 'created_at'
    }
    await session.execute(insert(Summary).values(**values).on_conflict_do_nothing(index_elements=['message_id']))
