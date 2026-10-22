# chat-server/app/conversations/repository.py

"""
대화와 그 사본들을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

대화를 읽는 함수는 주인의 ID 와 볼 수 있는 등급을 받는다. 대화의 ID 만으로 남의 대화를 읽는 길이 없다.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.conversations.models import Conversation, ConversationPersona, ImportedCharacter, Message
from app.ratings import Rating

# 대화 하나를 읽을 때 함께 오는 것: 대화, 판의 사본, 페르소나의 사본(없으면 None)
ConversationRow = tuple[Conversation, ImportedCharacter, ConversationPersona | None]


def add(session: AsyncSession, row: Conversation | ConversationPersona | Message) -> None:
    """새 행을 세션에 올린다."""
    session.add(row)


async def last_persona_source(session: AsyncSession, owner_id: uuid.UUID) -> uuid.UUID | None:
    """
    이 사람이 가장 최근에 시작한 대화의 페르소나(asset 서버의 id). 대화가 없거나 그 대화에 페르소나가 없었으면 None.

    지운 대화도 센다. "지난번에 고른 것"이다.
    """
    query = (
        select(ConversationPersona.source_id)
        .select_from(Conversation)
        .outerjoin(ConversationPersona, ConversationPersona.conversation_id == Conversation.id)
        .where(Conversation.owner_id == owner_id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(1)
    )
    return await session.scalar(query)


async def last_model(session: AsyncSession, owner_id: uuid.UUID) -> str | None:
    """
    이 사람이 가장 최근에 시작한 대화의 모델(이름표). 대화가 없거나 그 대화에 모델이 없었으면 None.

    지운 대화도 센다. "지난번에 고른 것"이다. 페르소나와 같다(last_persona_source).
    """
    query = (
        select(Conversation.model_slug)
        .where(Conversation.owner_id == owner_id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(1)
    )
    return await session.scalar(query)


async def set_model(session: AsyncSession, conversation_id: uuid.UUID, slug: str) -> None:
    """
    대화의 모델을 적는다. 수정 시각(updated_at)은 그대로 둔다.
    목록은 최근에 말한 것부터라 모델을 바꿨다고 앞으로 오지 않는다.

    ORM 의 객체를 고치면 onupdate 가 수정 시각을 바꾸므로 UPDATE 를 바로 쓴다. 칸에 제 값을 적어 onupdate 를 막는다.
    """
    statement = (
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(model_slug=slug, updated_at=Conversation.updated_at)
        .execution_options(synchronize_session=False)
    )
    await session.execute(statement)


async def keep_character(session: AsyncSession, character: ImportedCharacter) -> ImportedCharacter:
    """
    판의 사본을 둔다. 그 사람이 같은 판을 이미 가져왔으면 있는 것을 돌려준다.

    두 요청이 같은 판을 동시에 가져와도 하나만 남는다. 넣다가 겹치면 넣지 않고(ON CONFLICT DO NOTHING) 있는 것을 읽는다.
    """
    values = {
        'id': character.id,
        'owner_id': character.owner_id,
        'source_id': character.source_id,
        'version': character.version,
        'name': character.name,
        'rating': character.rating,
        'document': character.document,
    }
    statement = (
        insert(ImportedCharacter)
        .values(values)
        .on_conflict_do_nothing(index_elements=['owner_id', 'source_id', 'version'])
    )
    await session.execute(statement)
    query = select(ImportedCharacter).where(
        ImportedCharacter.owner_id == character.owner_id,
        ImportedCharacter.source_id == character.source_id,
        ImportedCharacter.version == character.version,
    )
    return (await session.scalars(query)).one()


def visible(owner_id: uuid.UUID, ratings: Sequence[Rating]) -> Select:
    """이 사람의 지우지 않은 대화 가운데 볼 수 있는 등급의 것. 대화와 판의 사본을 함께 고른다."""
    return (
        select(Conversation, ImportedCharacter)
        .join(ImportedCharacter, ImportedCharacter.id == Conversation.character_id)
        .where(
            Conversation.owner_id == owner_id,
            Conversation.deleted_at.is_(None),
            ImportedCharacter.rating.in_([rating.value for rating in ratings]),
        )
    )


async def list_visible(
    session: AsyncSession,
    owner_id: uuid.UUID,
    ratings: Sequence[Rating],
    source_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[Conversation, ImportedCharacter]], int]:
    """대화의 한 쪽(최근에 말한 것부터)과 전체 개수. source_id 를 주면 그 캐릭터(asset 서버의 id)의 대화만이다."""
    query = visible(owner_id, ratings)
    if source_id is not None:
        query = query.where(ImportedCharacter.source_id == source_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    page = query.order_by(Conversation.updated_at.desc(), Conversation.id).limit(limit).offset(offset)
    rows = await session.execute(page)
    return [(conversation, character) for conversation, character in rows.all()], total or 0


async def find_visible(
    session: AsyncSession, owner_id: uuid.UUID, ratings: Sequence[Rating], conversation_id: uuid.UUID
) -> ConversationRow | None:
    """이 사람의 대화 하나와 그 사본들. 없거나, 남의 것이거나, 지웠거나, 볼 수 없는 등급이면 None."""
    query = (
        visible(owner_id, ratings)
        .add_columns(ConversationPersona)
        .outerjoin(ConversationPersona, ConversationPersona.conversation_id == Conversation.id)
        .where(Conversation.id == conversation_id)
    )
    row = (await session.execute(query)).first()
    return None if row is None else (row[0], row[1], row[2])


async def active_path(session: AsyncSession, leaf_id: uuid.UUID | None) -> list[Message]:
    """
    가지의 끝(leaf_id)에서 첫 말까지 거슬러 올라간 말들. 첫 말부터 차례로 돌려준다. 끝이 없으면 빈 목록이다.

    대화의 말을 전부 읽지 않는다. 재귀 쿼리(WITH RECURSIVE)로 이 가지의 말만 읽는다. 대안이 많아도 읽는 양이 같다.
    """
    if leaf_id is None:
        return []
    # 끝에서 몇 걸음 올라왔는가(depth). 첫 말이 가장 깊다. 시각으로 줄 세우지 않는다.
    # 한 트랜잭션에 적힌 말들은 시각(now())이 같다
    upward = (
        select(Message.id, Message.parent_id, literal(0).label('depth'))
        .where(Message.id == leaf_id)
        .cte('path', recursive=True)
    )
    parent = aliased(Message)
    upward = upward.union_all(
        select(parent.id, parent.parent_id, upward.c.depth + 1).join(upward, parent.id == upward.c.parent_id)
    )
    query = select(Message).join(upward, Message.id == upward.c.id).order_by(upward.c.depth.desc())
    return list(await session.scalars(query))


async def find_visible_message(
    session: AsyncSession, owner_id: uuid.UUID, ratings: Sequence[Rating], message_id: uuid.UUID
) -> tuple[Message, ConversationRow] | None:
    """이 사람이 볼 수 있는 대화의 말 하나와 그 대화. 없거나 남의 대화의 말이면 None."""
    message = await session.get(Message, message_id)
    if message is None:
        return None
    row = await find_visible(session, owner_id, ratings, message.conversation_id)
    return None if row is None else (message, row)


async def alternatives(
    session: AsyncSession, conversation_id: uuid.UUID, parent_ids: Sequence[uuid.UUID | None]
) -> dict[uuid.UUID | None, list[uuid.UUID]]:
    """
    부모마다 그 아래의 말들(서로의 대안). 먼저 생긴 것부터. 첫 말들(부모가 없다)은 None 의 자리다.

    지금 가지의 말들의 부모를 한꺼번에 넘긴다. 쿼리 한 번이다(색인 ix_messages_conversation_parent).
    """
    parents = [parent for parent in parent_ids if parent is not None]
    query = (
        select(Message.parent_id, Message.id)
        .where(
            Message.conversation_id == conversation_id,
            Message.parent_id.in_(parents) | (Message.parent_id.is_(None) if None in parent_ids else False),
        )
        .order_by(Message.created_at, Message.id)
    )
    found: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for parent_id, message_id in (await session.execute(query)).all():
        found.setdefault(parent_id, []).append(message_id)
    return found


async def latest_descendant(session: AsyncSession, message_id: uuid.UUID) -> uuid.UUID:
    """
    그 말 아래에서 가장 나중에 생긴 말(그 말 자신일 수도 있다). 그 가지를 마지막으로 보던 곳이다.

    가장 나중에 생긴 말은 자식이 없다(자식은 언제나 부모보다 늦다). 그래서 그 가지의 끝이다.
    """
    downward = select(Message.id, Message.created_at).where(Message.id == message_id).cte('branch', recursive=True)
    child = aliased(Message)
    downward = downward.union_all(select(child.id, child.created_at).join(downward, child.parent_id == downward.c.id))
    query = select(downward.c.id).order_by(downward.c.created_at.desc(), downward.c.id.desc()).limit(1)
    return (await session.execute(query)).scalar_one()


async def set_leaf(session: AsyncSession, conversation_id: uuid.UUID, leaf_id: uuid.UUID, busy_since: datetime) -> bool:
    """
    지금 가지의 끝을 바꾼다(다른 대안을 본다). 답을 쓰는 중이면(busy_since 뒤에 차례를 잡았다) 바꾸지 않고 False.
    수정 시각은 그대로다. 말한 것이 아니라 보는 곳만 바꿨다.

    확인과 바꾸기를 한 문장으로 한다. 따로 하면 그사이 시작한 답이 끝나며 가지의 끝을 덮는다.
    """
    statement = (
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            or_(Conversation.generating_since.is_(None), Conversation.generating_since < busy_since),
        )
        .values(active_leaf_id=leaf_id, updated_at=Conversation.updated_at)
        .returning(Conversation.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).first() is not None
