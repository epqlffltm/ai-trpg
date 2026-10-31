# story-server/app/conversations/copying.py

"""
플레이 복사(docs/architecture/story.md 의 "세션과 기록"). 지금 보고 있는 가지를 새 세션으로 복사한다.

상태가 말에 붙어 있어 가지 하나를 복사하면 그 시점부터 이어 할 수 있다(엔진은 다시 판정하지 않는다).

  - 복사하는 것: 지금 가지의 말들(첫 말부터 끝까지, 말의 글과 조각, 장면의 인물, 열린 이벤트와 본 엔딩, 고친 표시,
    다음 답 추천, 처음의 시각)과 말에 붙은 상태, 그 말들에 붙은 요약, 기억 메모(제안까지), 페르소나의 사본,
    세션의 모델, 세션에 굳힌 계정의 본 엔딩(같은 회차를 이어 가는 것이다)
  - 복사하지 않는 것: 다른 가지(대안), 청구 기록(generations, 다시 청구하지 않는다), 신고, 지운 표시.
    요약의 원가와 토큰 수도 옮기지 않는다(원가는 원래 세션이 이미 냈다)
  - 판의 사본(worlds)은 같은 것을 가리킨다. 사람마다, 판마다 하나라 복사하지 않는다(로어북의 벡터도 함께 쓴다)
  - 원래 세션을 잠그고 복사한다. 답을 쓰는 중이면 409 generation_in_progress 다(반쯤 쓴 답을 복사하지 않는다).
    잠근 동안에는 새 말이 차례를 잡지 못한다(app/turns/repository.py)
  - 한 트랜잭션이다. 계정의 기록(본 엔딩, 연 일러스트)은 계정에 하나라 바꾸지 않는다
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations import repository
from app.conversations.models import Conversation, ConversationPersona, Message, MessageState
from app.conversations.service import GENERATION_STALE, ConversationBusyError, get_conversation
from app.core.dependencies import Viewer
from app.memory import repository as memory
from app.memory.models import MemoryNote, Summary

# 복사한 세션의 제목에 붙이는 말. 목록에서 원래 세션과 가린다
COPY_SUFFIX = ' (복사)'


def copy_title(title: str) -> str:
    """복사한 세션의 제목."""
    return f'{title}{COPY_SUFFIX}'


def is_busy(conversation: Conversation, now: datetime) -> bool:
    """답을 쓰는 중인가. 차례를 쥔 지 GENERATION_STALE 이 지났으면 아니다(서버가 꺼졌다)."""
    since = conversation.generating_since
    return since is not None and since >= now - GENERATION_STALE


def build_copy(source: Conversation) -> Conversation:
    """새 세션. 같은 사람, 같은 판의 사본, 같은 모델, 같은 굳힌 엔딩이다. 가지의 끝은 말을 넣은 뒤에 잇는다."""
    return Conversation(
        id=uuid.uuid4(),
        owner_id=source.owner_id,
        world_id=source.world_id,
        title=copy_title(source.title),
        model_slug=source.model_slug,
        cleared_endings=list(source.cleared_endings or ()),
    )


def new_ids(path: Sequence[Message]) -> dict[uuid.UUID, uuid.UUID]:
    """원래 말의 id → 복사한 말의 id."""
    return {message.id: uuid.uuid4() for message in path}


def copied_messages(
    path: Sequence[Message], ids: dict[uuid.UUID, uuid.UUID], conversation_id: uuid.UUID
) -> list[Message]:
    """
    가지의 말들의 복사(첫 말부터). 부모는 복사한 말을 가리킨다. 시각은 원래 것 그대로다
    (대안과 가지의 끝을 시각으로 고르는 곳이 있다, app/conversations/repository.py 의 latest_descendant).
    """
    return [
        Message(
            id=ids[message.id],
            conversation_id=conversation_id,
            parent_id=ids.get(message.parent_id) if message.parent_id is not None else None,
            role=message.role,
            content=message.content,
            status=message.status,
            segments=list(message.segments or ()),
            cast=list(message.cast or ()),
            event_id=message.event_id,
            ending_id=message.ending_id,
            edited=message.edited,
            suggestions=list(message.suggestions or ()),
            created_at=message.created_at,
        )
        for message in path
    ]


def copied_states(
    path: Sequence[Message], states: Sequence[dict | None], ids: dict[uuid.UUID, uuid.UUID]
) -> list[MessageState]:
    """말에 붙은 상태의 복사. 상태가 없는 말은 건너뛴다. states 는 path 와 같은 차례다."""
    return [
        MessageState(message_id=ids[message.id], state=dict(state))
        for message, state in zip(path, states, strict=True)
        if state is not None
    ]


def copied_persona(persona: ConversationPersona | None, conversation_id: uuid.UUID) -> ConversationPersona | None:
    """페르소나의 사본의 복사. 페르소나 없이 시작한 세션이면 None."""
    if persona is None:
        return None
    return ConversationPersona(
        conversation_id=conversation_id,
        source_id=persona.source_id,
        revision=persona.revision,
        name=persona.name,
        description=persona.description,
        image_id=persona.image_id,
        age=persona.age,
        gender=persona.gender,
        form_of_address=persona.form_of_address,
        speech_examples=persona.speech_examples,
        personality=persona.personality,
    )


def copied_notes(notes: Sequence[MemoryNote], conversation_id: uuid.UUID) -> list[MemoryNote]:
    """기억 메모의 복사. 쓴 사람(사용자, 요약의 제안)과 받아들인 때도 그대로다."""
    return [
        MemoryNote(
            conversation_id=conversation_id,
            text=note.text,
            source=note.source,
            accepted_at=note.accepted_at,
            created_at=note.created_at,
        )
        for note in notes
    ]


def copied_summaries(
    summaries: Sequence[Summary], ids: dict[uuid.UUID, uuid.UUID], conversation_id: uuid.UUID
) -> list[Summary]:
    """가지의 말에 붙은 요약의 복사. 원가와 토큰 수는 옮기지 않는다(원래 세션이 이미 냈다)."""
    return [
        Summary(
            message_id=ids[summary.message_id],
            conversation_id=conversation_id,
            text=summary.text,
            model_slug=summary.model_slug,
        )
        for summary in summaries
        if summary.message_id in ids
    ]


async def copy_conversation(
    session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, now: datetime
) -> uuid.UUID:
    """
    지금 가지를 새 세션으로 복사하고 새 세션의 id 를 돌려준다.
    없거나 남의 것이면 ConversationNotFoundError, 답을 쓰는 중이면 ConversationBusyError.
    """
    source, _ = await get_conversation(session, viewer, conversation_id)
    await repository.lock_conversation(session, source.id)
    await session.refresh(source)
    if is_busy(source, now):
        await session.rollback()
        raise ConversationBusyError
    path = await repository.active_path(session, source.active_leaf_id)
    path_ids = [message.id for message in path]
    states = await repository.states_on(session, path_ids)
    persona = await repository.persona_of(session, source.id)
    notes = await memory.list_notes(session, source.id)
    summaries = await memory.summary_rows(session, path_ids)
    copy = build_copy(source)
    ids = new_ids(path)
    repository.add(session, copy)
    await session.flush()
    session.add_all(copied_messages(path, ids, copy.id))
    await session.flush()
    session.add_all(copied_states(path, states, ids))
    session.add_all(copied_notes(notes, copy.id))
    session.add_all(copied_summaries(summaries, ids, copy.id))
    persona_copy = copied_persona(persona, copy.id)
    if persona_copy is not None:
        session.add(persona_copy)
    copy.active_leaf_id = ids[source.active_leaf_id] if source.active_leaf_id is not None else None
    await session.commit()
    return copy.id
