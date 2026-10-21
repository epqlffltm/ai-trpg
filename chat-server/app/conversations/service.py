# chat-server/app/conversations/service.py

"""
대화를 시작하고, 목록으로 내주고, 하나를 읽고, 지운다(docs/architecture/chat-server.md 의 만드는 순서 1).

대화를 시작하는 길.
  1. 지난번 대화의 페르소나를 읽는다(사람이 페르소나를 고르지 않았을 때만). 읽은 뒤 트랜잭션을 닫는다
  2. asset 서버에서 캐릭터의 마지막 판과 페르소나의 사본을 가져온다. DB 연결을 쥐지 않은 채로 부른다
  3. 시작 상황을 고른다. 판에 없는 번호면 StartNotFoundError(422)
  4. 판의 사본(사람마다, 판마다 하나), 대화, 페르소나의 사본, 첫 말(인사말)을 한 트랜잭션에서 저장한다
쓸 수 있는 캐릭터인지는 asset 서버가 판단한다. 가져온 판의 등급도 여기서 한 번 더 본다(allowed_ratings).

지키는 것.
  - 남의 대화는 없는 것과 같다(ConversationNotFoundError, 404). 볼 수 없는 등급의 대화도 그렇다.
  - 사본은 가져온 뒤 바뀌지 않는다. 원본이 바뀌어도 그대로다.
  - 지우면 지운 시각만 적는다. 말과 사본은 남는다(기록의 처리는 열린 질문, 탈퇴는 그 PR 이 정한다).
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.client import AssetAdultRequiredError, AssetClient, AssetNotFoundError
from app.assets.schemas import CharacterCopy, PersonaCopy, StartDocument
from app.conversations import repository
from app.conversations.models import (
    Conversation,
    ConversationPersona,
    ImportedCharacter,
    Message,
    MessageStatus,
    Role,
)
from app.conversations.repository import ConversationRow
from app.conversations.schemas import ConversationCreate
from app.core.dependencies import Viewer
from app.ratings import allowed_ratings


class ConversationNotFoundError(Exception):
    """그런 대화가 없다. 남의 것, 지운 것, 볼 수 없는 등급의 것도 이것이다."""


class CharacterNotFoundError(Exception):
    """asset 서버가 그 캐릭터를 쓸 수 없다고 했다(없다, 남의 비공개다, 게시한 적이 없다, 볼 수 없는 등급이다)."""


class PersonaNotFoundError(Exception):
    """고른 페르소나가 없다(남의 것도)."""


class AdultContentRequiredError(Exception):
    """자기 캐릭터인데 등급을 쓸 수 없다. 화면이 본인인증으로 안내한다(403)."""


class StartNotFoundError(Exception):
    """판에 그 번호의 시작 상황이 없다. count 는 판의 시작 상황의 수다."""

    def __init__(self, count: int) -> None:
        super().__init__(count)
        self.count = count


# --- 고르기와 만들기. DB 와 바깥을 모른다 ---


def pick_start(copy: CharacterCopy, index: int) -> StartDocument:
    """판의 시작 상황 하나. 그 번호가 없으면 StartNotFoundError."""
    starts = copy.document.starts
    if index >= len(starts):
        raise StartNotFoundError(len(starts))
    return starts[index]


def require_usable_rating(copy: CharacterCopy, viewer: Viewer) -> None:
    """가져온 판의 등급을 이 사람이 쓸 수 있는가. asset 서버가 이미 봤지만 이 서버의 규칙으로 한 번 더 본다."""
    if copy.rating not in allowed_ratings(viewer.claims):
        raise CharacterNotFoundError


def build_character(owner_id: uuid.UUID, copy: CharacterCopy) -> ImportedCharacter:
    """판의 사본을 만든다. 아직 저장하지 않는다."""
    return ImportedCharacter(
        id=uuid.uuid4(),
        owner_id=owner_id,
        source_id=copy.id,
        version=copy.version,
        name=copy.document.name,
        rating=copy.rating,
        document=copy.document.model_dump(mode='json'),
    )


def build_conversation(owner_id: uuid.UUID, character: ImportedCharacter, start: StartDocument) -> Conversation:
    """대화를 만든다. 제목은 캐릭터의 이름이다. 아직 저장하지 않는다."""
    return Conversation(
        id=uuid.uuid4(),
        owner_id=owner_id,
        character_id=character.id,
        title=character.name,
        start_title=start.title,
        start_situation=start.situation,
    )


def build_persona(conversation_id: uuid.UUID, copy: PersonaCopy) -> ConversationPersona:
    """페르소나의 사본을 만든다. 아직 저장하지 않는다."""
    return ConversationPersona(
        conversation_id=conversation_id,
        source_id=copy.id,
        revision=copy.revision,
        name=copy.name,
        description=copy.description,
        image_id=copy.image_id,
        age=copy.age,
        gender=copy.gender,
        form_of_address=copy.form_of_address,
        speech_examples=copy.speech_examples,
        personality=copy.personality,
    )


def build_opening(conversation_id: uuid.UUID, greeting: str) -> Message | None:
    """첫 말. 캐릭터가 먼저 하는 인사말이다. 인사말이 비어 있으면 첫 말이 없다(None)."""
    if not greeting.strip():
        return None
    return Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role=Role.ASSISTANT,
        content=greeting,
        status=MessageStatus.COMPLETE,
    )


# --- asset 서버를 부르기 ---


async def fetch_character(asset: AssetClient, viewer: Viewer, character_id: uuid.UUID) -> CharacterCopy:
    """캐릭터의 마지막 판. asset 서버의 404 와 403 을 이 서버의 예외로 바꾼다. 닿지 못하면 AssetUnavailableError."""
    try:
        return await asset.fetch_character(viewer.token, character_id)
    except AssetNotFoundError as error:
        raise CharacterNotFoundError from error
    except AssetAdultRequiredError as error:
        raise AdultContentRequiredError from error


async def fetch_chosen_persona(asset: AssetClient, viewer: Viewer, persona_id: uuid.UUID | None) -> PersonaCopy | None:
    """사람이 고른 페르소나의 사본. 고르지 않았으면(None) None, 없으면 PersonaNotFoundError."""
    if persona_id is None:
        return None
    try:
        return await asset.fetch_persona(viewer.token, persona_id)
    except AssetNotFoundError as error:
        raise PersonaNotFoundError from error


async def fetch_last_persona(asset: AssetClient, viewer: Viewer, persona_id: uuid.UUID | None) -> PersonaCopy | None:
    """지난번 대화의 페르소나의 사본. 지난번에 없었거나 그사이에 지워졌으면 None 이다(페르소나 없이 시작한다)."""
    try:
        return await fetch_chosen_persona(asset, viewer, persona_id)
    except PersonaNotFoundError:
        return None


# --- 저장과 읽기 ---


async def persona_to_fetch(session: AsyncSession, viewer: Viewer, data: ConversationCreate) -> uuid.UUID | None:
    """
    가져올 페르소나. 고르지 않았으면 지난번 대화의 것이다.

    읽은 뒤 트랜잭션을 닫는다. asset 서버를 부르는 동안 DB 연결을 쥐고 있지 않게 한다.
    """
    if data.persona_chosen():
        return data.persona_id
    persona_id = await repository.last_persona_source(session, viewer.claims.user_id)
    await session.rollback()
    return persona_id


async def save_conversation(
    session: AsyncSession, owner_id: uuid.UUID, copy: CharacterCopy, start: StartDocument, persona: PersonaCopy | None
) -> uuid.UUID:
    """판의 사본, 대화, 페르소나의 사본, 첫 말을 한 번에 저장하고 대화의 id 를 돌려준다."""
    character = await repository.keep_character(session, build_character(owner_id, copy))
    conversation = build_conversation(owner_id, character, start)
    repository.add(session, conversation)
    if persona is not None:
        repository.add(session, build_persona(conversation.id, persona))
    opening = build_opening(conversation.id, copy.document.greeting)
    if opening is not None:
        # 말이 먼저 저장되어야 대화가 그것을 가리킬 수 있다(서로 가리킨다)
        await session.flush()
        repository.add(session, opening)
        await session.flush()
        conversation.active_leaf_id = opening.id
    await session.commit()
    return conversation.id


async def start_conversation(
    session: AsyncSession, asset: AssetClient, viewer: Viewer, data: ConversationCreate
) -> uuid.UUID:
    """대화를 시작하고 그 id 를 돌려준다. 실패하면 위의 예외들이나 AssetUnavailableError."""
    persona_id = await persona_to_fetch(session, viewer, data)
    copy = await fetch_character(asset, viewer, data.character_id)
    require_usable_rating(copy, viewer)
    start = pick_start(copy, data.start)
    if data.persona_chosen():
        persona = await fetch_chosen_persona(asset, viewer, persona_id)
    else:
        persona = await fetch_last_persona(asset, viewer, persona_id)
    return await save_conversation(session, viewer.claims.user_id, copy, start, persona)


async def get_conversation(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> ConversationRow:
    """이 사람의 대화 하나와 그 사본들. 없으면 ConversationNotFoundError."""
    found = await repository.find_visible(
        session, viewer.claims.user_id, allowed_ratings(viewer.claims), conversation_id
    )
    if found is None:
        raise ConversationNotFoundError
    return found


async def list_conversations(
    session: AsyncSession, viewer: Viewer, source_id: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[tuple[Conversation, ImportedCharacter]], int]:
    """이 사람의 대화의 한 쪽과 전체 개수. 볼 수 있는 등급만이다."""
    return await repository.list_visible(
        session, viewer.claims.user_id, allowed_ratings(viewer.claims), source_id, limit, offset
    )


async def read_messages(session: AsyncSession, conversation: Conversation) -> list[Message]:
    """지금 보고 있는 가지의 말들. 첫 말부터."""
    return await repository.active_path(session, conversation.active_leaf_id)


async def delete_conversation(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> None:
    """대화를 지운다(지운 시각을 적는다). 없으면 ConversationNotFoundError."""
    conversation, _, _ = await get_conversation(session, viewer, conversation_id)
    conversation.deleted_at = func.now()
    await session.commit()
