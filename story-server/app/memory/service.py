# story-server/app/memory/service.py

"""
기억 메모를 보고, 더하고, 고치고, 지운다. 세션의 주인만 한다(남의 세션은 ConversationNotFoundError, 404).

답을 쓰는 중에도 고칠 수 있다. 고친 것은 다음 말부터 모델에 간다(chat 과 같다).
세션 하나에 메모는 NOTES_PER_CONVERSATION 개까지다. 늘 모델에 가는 글이라 입력의 양을 지킨다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.service import get_conversation
from app.core.dependencies import Viewer
from app.memory import repository
from app.memory.models import NOTES_PER_CONVERSATION, MemoryNote


class NoteNotFoundError(Exception):
    """그런 메모가 없다(404 note_not_found). 다른 세션의 메모도 이것이다."""


class NotesFullError(Exception):
    """세션의 메모가 가득 찼다(409 notes_full). 지우고 더한다."""


async def list_notes(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> list[MemoryNote]:
    """세션의 메모들. 먼저 쓴 것부터."""
    conversation, _ = await get_conversation(session, viewer, conversation_id)
    return await repository.list_notes(session, conversation.id)


async def add_note(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, text: str) -> MemoryNote:
    """메모를 더한다. 가득 찼으면 NotesFullError. 세션을 잠그고 센다."""
    conversation, _ = await get_conversation(session, viewer, conversation_id)
    await repository.lock_conversation(session, conversation.id)
    if await repository.count_notes(session, conversation.id) >= NOTES_PER_CONVERSATION:
        raise NotesFullError
    note = MemoryNote(id=uuid.uuid4(), conversation_id=conversation.id, text=text)
    repository.add_note(session, note)
    await session.commit()
    await session.refresh(note)
    return note


async def get_note(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, note_id: uuid.UUID) -> MemoryNote:
    """그 세션의 메모 하나. 없으면 NoteNotFoundError."""
    conversation, _ = await get_conversation(session, viewer, conversation_id)
    note = await repository.find_note(session, conversation.id, note_id)
    if note is None:
        raise NoteNotFoundError
    return note


async def edit_note(
    session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, note_id: uuid.UUID, text: str
) -> MemoryNote:
    """메모의 글을 고친다."""
    note = await get_note(session, viewer, conversation_id, note_id)
    note.text = text
    await session.commit()
    await session.refresh(note)
    return note


async def delete_note(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, note_id: uuid.UUID) -> None:
    """메모를 지운다."""
    note = await get_note(session, viewer, conversation_id, note_id)
    await repository.delete_note(session, note.id)
    await session.commit()


async def notes_for_prompt(session: AsyncSession, conversation_id: uuid.UUID) -> list[str]:
    """모델에 보낼 메모의 글들. 먼저 쓴 것부터."""
    return [note.text for note in await repository.list_notes(session, conversation_id)]


def render_memory(texts: list[str]) -> str | None:
    """'[기억]' 블록. 메모가 없으면 None. 순수 함수다(chat 과 같은 모양)."""
    if not texts:
        return None
    return '\n'.join(['[기억]', *(f'- {text}' for text in texts)])
