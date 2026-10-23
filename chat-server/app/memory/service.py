# chat-server/app/memory/service.py

"""
기억 메모를 보고, 더하고, 고치고, 지운다. 지금 가지의 요약을 읽는다.
대화의 주인만 한다(남의 대화는 ConversationNotFoundError, 404).

답을 쓰는 중에도 고칠 수 있다. 고친 것은 다음 말부터 모델에 간다(화면 명세 C5).
대화 하나에 메모는 NOTES_PER_CONVERSATION 개까지다. 늘 모델에 가는 글이라 입력의 양을 지킨다.
요약이 제안한 메모(#677)는 받아들이기 전에는 모델에 가지 않고 이 수에 들지 않는다.
받아들이면(accept_note) 그때 수에 든다. 버리기는 지우기다. 제안은 대화마다 PROPOSALS_PER_CONVERSATION 개까지 쌓인다.
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations import repository as conversations
from app.conversations.service import get_conversation
from app.core.dependencies import Viewer
from app.memory import repository
from app.memory.models import NOTES_PER_CONVERSATION, PROPOSALS_PER_CONVERSATION, MemoryNote, NoteSource, Summary
from app.memory.summaries import pick_proposals


class NoteNotFoundError(Exception):
    """그런 메모가 없다(404). 다른 대화의 메모도 이것이다."""


class NotesFullError(Exception):
    """대화의 메모가 가득 찼다(409). 지우고 더한다."""


async def list_notes(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> list[MemoryNote]:
    """대화의 메모들. 먼저 쓴 것부터."""
    conversation, _, _ = await get_conversation(session, viewer, conversation_id)
    return await repository.list_notes(session, conversation.id)


async def add_note(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, text: str) -> MemoryNote:
    """메모를 더한다. 사용자가 쓴 것이다. 가득 찼으면 NotesFullError. 대화를 잠그고 센다."""
    conversation, _, _ = await get_conversation(session, viewer, conversation_id)
    await repository.lock_conversation(session, conversation.id)
    if await repository.count_notes(session, conversation.id) >= NOTES_PER_CONVERSATION:
        raise NotesFullError
    note = MemoryNote(id=uuid.uuid4(), conversation_id=conversation.id, text=text, source=NoteSource.USER)
    repository.add_note(session, note)
    await session.commit()
    await session.refresh(note)
    return note


async def get_note(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, note_id: uuid.UUID) -> MemoryNote:
    """그 대화의 메모 하나. 없으면 NoteNotFoundError."""
    conversation, _, _ = await get_conversation(session, viewer, conversation_id)
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


async def accept_note(
    session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, note_id: uuid.UUID, now: datetime
) -> MemoryNote:
    """
    요약이 제안한 메모를 받아들인다. 다음 말부터 모델에 간다. 이미 모델에 가는 메모면 그대로 돌려준다.
    메모가 가득 찼으면 NotesFullError. 대화를 잠그고 센다.
    """
    note = await get_note(session, viewer, conversation_id, note_id)
    if not note.pending:
        return note
    await repository.lock_conversation(session, note.conversation_id)
    if await repository.count_notes(session, note.conversation_id) >= NOTES_PER_CONVERSATION:
        raise NotesFullError
    note.accepted_at = now
    await session.commit()
    await session.refresh(note)
    return note


async def add_proposals(session: AsyncSession, conversation_id: uuid.UUID, lines: list[str]) -> list[MemoryNote]:
    """
    요약이 제안한 메모 줄들을 제안으로 더한다(커밋하지 않는다). 대화를 잠근 뒤 지금의 메모와 견주어 겹치는 것을 거르고,
    기다리는 제안이 상한을 넘지 않게 자른다. 더한 것들을 돌려준다.
    """
    await repository.lock_conversation(session, conversation_id)
    known = [note.text for note in await repository.list_notes(session, conversation_id)]
    room = PROPOSALS_PER_CONVERSATION - await repository.count_proposals(session, conversation_id)
    texts = pick_proposals(lines, known)[: max(room, 0)]
    notes = [
        MemoryNote(id=uuid.uuid4(), conversation_id=conversation_id, text=text, source=NoteSource.SUMMARY)
        for text in texts
    ]
    for note in notes:
        repository.add_note(session, note)
    return notes


async def delete_note(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, note_id: uuid.UUID) -> None:
    """메모를 지운다."""
    note = await get_note(session, viewer, conversation_id, note_id)
    await repository.delete_note(session, note.id)
    await session.commit()


async def notes_for_prompt(session: AsyncSession, conversation_id: uuid.UUID) -> list[str]:
    """모델에 보낼 메모의 글들. 사용자가 쓴 것과 받아들인 제안이다(받아들이기를 기다리는 제안은 가지 않는다)."""
    notes = await repository.list_notes(session, conversation_id)
    return [note.text for note in notes if not note.pending]


def render_memory(texts: list[str]) -> str | None:
    """'[기억]' 블록. 메모가 없으면 None. 순수 함수다."""
    if not texts:
        return None
    return '\n'.join(['[기억]', *(f'- {text}' for text in texts)])


async def current_summary(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> Summary | None:
    """지금 가지에 붙은 요약 가운데 가장 뒤의 것. 없으면 None. 화면이 읽기만 한다(C5)."""
    conversation, _, _ = await get_conversation(session, viewer, conversation_id)
    path = await conversations.active_path(session, conversation.active_leaf_id)
    return await repository.latest_summary_row(session, [message.id for message in path])
