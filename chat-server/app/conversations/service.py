# chat-server/app/conversations/service.py

"""
대화를 시작하고, 목록으로 내주고, 하나를 읽고, 모델을 바꾸고, 지운다
(docs/architecture/chat-server.md 의 만드는 순서 1, 2).

대화를 시작하는 길.
  1. 지난번 대화의 페르소나와 모델을 읽는다(사람이 고르지 않은 것만). 읽은 뒤 트랜잭션을 닫는다
  2. asset 서버에서 캐릭터의 마지막 판과 페르소나의 사본을 가져온다. DB 연결을 쥐지 않은 채로 부른다
  3. 시작 상황을 고른다. 판에 없는 번호면 StartNotFoundError(422)
  4. 모델을 정한다. 판의 등급을 알아야 해서 판을 가져온 뒤다. 고른 모델을 쓸 수 없으면 ModelUnavailableError(422),
     지난번 모델을 쓸 수 없으면 모델 없이 시작한다
  5. 판의 사본(사람마다, 판마다 하나), 대화, 페르소나의 사본, 첫 말(인사말)을 한 트랜잭션에서 저장한다
쓸 수 있는 캐릭터인지는 asset 서버가 판단한다. 가져온 판의 등급도 여기서 한 번 더 본다(allowed_ratings).

모델은 고르거나 바꿀 때 한 번 본다. 모델 목록에서 고를 수 있고(app/catalog/choice.py) 결제 서버가 팔고 있어야 한다
(app/catalog/offers.py 의 is_sold). 그 뒤 꺼지거나 은퇴하거나 판매를 멈춰도 대화는 그 모델을 가리킨 채로 두고,
읽을 때 "더는 쓸 수 없다"(usable)를 함께 내준다. 몰래 다른 모델로 바꾸지 않는다.
결제 서버의 가격 목록은 받아 둔 것을 쓴다. 사람이 고른 모델은 가격 목록이 있어야 정한다(없으면 503).
지난번 모델과 읽을 때의 usable 은 가격 목록을 받지 못하면 팔고 있다고 본다. 말을 보낼 때 결제 서버가 다시 본다.

지키는 것.
  - 남의 대화는 없는 것과 같다(ConversationNotFoundError, 404). 볼 수 없는 등급의 대화도 그렇다.
  - 사본은 가져온 뒤 바뀌지 않는다. 원본이 바뀌어도 그대로다.
  - 지우면 지운 시각만 적는다. 말과 사본은 남는다(기록의 처리는 열린 질문, 탈퇴는 그 PR 이 정한다).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.client import AssetAdultRequiredError, AssetClient, AssetNotFoundError
from app.assets.schemas import CharacterCopy, PersonaCopy, StartDocument
from app.billing.price_list import PriceList, PriceListUnavailable
from app.billing.prices import PriceBook
from app.catalog import repository as catalog
from app.catalog.choice import is_choosable
from app.catalog.models import AiModel
from app.catalog.offers import is_sold
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
from app.ratings import Rating, allowed_ratings

# 차례(generating_since)를 쥔 채 이만큼 지나면 서버가 도중에 꺼진 것으로 본다.
# 모델을 부르는 시간의 상한(LLM_TIMEOUT_SECONDS, 10분까지)보다 길다
GENERATION_STALE = timedelta(minutes=15)


class ConversationNotFoundError(Exception):
    """그런 대화가 없다. 남의 것, 지운 것, 볼 수 없는 등급의 것도 이것이다."""


class CharacterNotFoundError(Exception):
    """asset 서버가 그 캐릭터를 쓸 수 없다고 했다(없다, 남의 비공개다, 게시한 적이 없다, 볼 수 없는 등급이다)."""


class PersonaNotFoundError(Exception):
    """고른 페르소나가 없다(남의 것도)."""


class AdultContentRequiredError(Exception):
    """자기 캐릭터인데 등급을 쓸 수 없다. 화면이 본인인증으로 안내한다(403)."""


class ModelUnavailableError(Exception):
    """고른 모델을 이 대화에 쓸 수 없다(없다, 꺼졌다, 은퇴했다, 성인 등급의 대화에 쓸 수 없다). 422 다."""


@dataclass(frozen=True)
class Remembered:
    """지난번 대화에서 가져올 것. 사람이 고른 것은 그 값이다. 비어 있으면 없이 시작한다."""

    persona_id: uuid.UUID | None
    model_slug: str | None


class ConversationBusyError(Exception):
    """대화가 답을 쓰는 중이다(409). 한 대화에 한 번에 하나의 생성만 받는다. 그동안 가지도 바꾸지 않는다."""


class MessageNotFoundError(Exception):
    """그런 말이 없다. 남의 대화의 말, 다른 대화의 말도 이것이다(404)."""


class NotEditableError(Exception):
    """
    그렇게 고칠 수 없는 말이다(422). 캐릭터의 말은 그 자리에서 고치고(PATCH),
    사람의 말은 새 가지로 고친다(말 보내기의 edit_of). 반대로 하면 이것이다.
    """


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


def build_conversation(
    owner_id: uuid.UUID, character: ImportedCharacter, start: StartDocument, model_slug: str | None
) -> Conversation:
    """대화를 만든다. 제목은 캐릭터의 이름이다. 아직 저장하지 않는다."""
    return Conversation(
        id=uuid.uuid4(),
        owner_id=owner_id,
        character_id=character.id,
        model_slug=model_slug,
        title=character.name,
        start_title=start.title,
        start_situation=start.situation,
        start_hour=start.hour,
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


def model_usable(model: AiModel, rating: Rating, book: PriceBook | None, now: datetime) -> bool:
    """
    그 모델을 그 등급의 대화에 now 에 고를 수 있나. 모델 목록에서 고를 수 있고 결제 서버가 팔고 있어야 한다.

    book 이 None 이면 값을 모르는 것이다(가격 목록을 받지 못했다). 그때는 팔고 있다고 본다.
    """
    if not is_choosable(model, rating, now.date()):
        return False
    return book is None or is_sold(book, model.slug, now)


def require_usable_model(model: AiModel | None, rating: Rating, book: PriceBook | None, now: datetime) -> AiModel:
    """고른 모델. 표에 없거나 이 대화에 고를 수 없으면 ModelUnavailableError."""
    if model is None or not model_usable(model, rating, book, now):
        raise ModelUnavailableError
    return model


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


async def remember_choices(session: AsyncSession, viewer: Viewer, data: ConversationCreate) -> Remembered:
    """
    쓸 페르소나와 모델. 고르지 않은 것은 지난번 대화의 것이다.

    읽은 뒤 트랜잭션을 닫는다. asset 서버를 부르는 동안 DB 연결을 쥐고 있지 않게 한다.
    """
    owner_id = viewer.claims.user_id
    if data.persona_chosen():
        persona_id = data.persona_id
    else:
        persona_id = await repository.last_persona_source(session, owner_id)
    model_slug = data.model if data.model_chosen() else await repository.last_model(session, owner_id)
    await session.rollback()
    return Remembered(persona_id, model_slug)


async def known_book(prices: PriceList) -> PriceBook | None:
    """가격 목록. 받지 못했고 받아 둔 것도 없으면 None 이다(값을 모른다)."""
    try:
        return await prices.book()
    except PriceListUnavailable:
        return None


async def book_for_choice(prices: PriceList, data: ConversationCreate, slug: str | None) -> PriceBook | None:
    """
    대화의 모델을 정할 때 쓰는 가격 목록. 정할 모델이 없으면 부르지 않는다(None).

    사람이 고른 모델이면 꼭 받아야 한다. 받지 못하면 PriceListUnavailable(503). 값을 모르는 모델을 고르게 하지 않는다.
    지난번 모델이면 받지 못해도 시작한다(None, 팔고 있다고 본다). 결제 서버가 내려가도 대화는 시작된다.
    """
    if slug is None:
        return None
    if data.model_chosen():
        return await prices.book()
    return await known_book(prices)


async def pick_model(
    session: AsyncSession,
    data: ConversationCreate,
    slug: str | None,
    rating: Rating,
    book: PriceBook | None,
    now: datetime,
) -> str | None:
    """
    대화의 모델을 정한다. 고른 모델을 쓸 수 없으면 ModelUnavailableError 다.
    지난번 모델을 쓸 수 없으면 없이(None) 시작한다.

    잠그지 않는다. 그사이에 모델이 꺼져도 대화는 그 모델을 가리킬 뿐이고, 읽을 때 usable 이 거짓으로 보인다.
    """
    if slug is None:
        return None
    model = await catalog.get_model(session, slug)
    if data.model_chosen():
        return require_usable_model(model, rating, book, now).slug
    return slug if model is not None and model_usable(model, rating, book, now) else None


async def save_conversation(
    session: AsyncSession,
    owner_id: uuid.UUID,
    copy: CharacterCopy,
    start: StartDocument,
    persona: PersonaCopy | None,
    model_slug: str | None,
) -> uuid.UUID:
    """판의 사본, 대화, 페르소나의 사본, 첫 말을 한 번에 저장하고 대화의 id 를 돌려준다."""
    character = await repository.keep_character(session, build_character(owner_id, copy))
    conversation = build_conversation(owner_id, character, start, model_slug)
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
    session: AsyncSession,
    asset: AssetClient,
    prices: PriceList,
    viewer: Viewer,
    data: ConversationCreate,
    now: datetime,
) -> uuid.UUID:
    """
    대화를 시작하고 그 id 를 돌려준다. 실패하면 위의 예외들이나 AssetUnavailableError, PriceListUnavailable.

    바깥(asset 서버, 결제 서버의 가격 목록)은 DB 의 트랜잭션을 열기 전에 부른다.
    """
    remembered = await remember_choices(session, viewer, data)
    copy = await fetch_character(asset, viewer, data.character_id)
    require_usable_rating(copy, viewer)
    start = pick_start(copy, data.start)
    if data.persona_chosen():
        persona = await fetch_chosen_persona(asset, viewer, remembered.persona_id)
    else:
        persona = await fetch_last_persona(asset, viewer, remembered.persona_id)
    book = await book_for_choice(prices, data, remembered.model_slug)
    model_slug = await pick_model(session, data, remembered.model_slug, Rating(copy.rating), book, now)
    return await save_conversation(session, viewer.claims.user_id, copy, start, persona, model_slug)


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


async def conversation_models(session: AsyncSession, conversations: list[Conversation]) -> dict[str, AiModel]:
    """대화들이 가리키는 모델들. 이름표로 찾는다. 모델이 없는 대화는 들지 않는다."""
    slugs = {conversation.model_slug for conversation in conversations if conversation.model_slug is not None}
    return await catalog.models_in(session, slugs)


async def change_model(
    session: AsyncSession, prices: PriceList, viewer: Viewer, conversation_id: uuid.UUID, slug: str, now: datetime
) -> AiModel:
    """
    대화의 모델을 바꾸고 그 모델을 돌려준다. 대화가 없으면 ConversationNotFoundError,
    고를 수 없으면 ModelUnavailableError, 가격 목록을 받지 못했으면 PriceListUnavailable 이다.

    바꾸는 순간부터 그 모델의 가격표로 청구한다(다음 말부터). 목록의 차례(최근에 말한 것부터)는 바꾸지 않는다.
    가격 목록은 DB 의 트랜잭션을 열기 전에 받는다.
    """
    book = await prices.book()
    conversation, character, _ = await get_conversation(session, viewer, conversation_id)
    model = require_usable_model(await catalog.get_model(session, slug), Rating(character.rating), book, now)
    await repository.set_model(session, conversation.id, model.slug)
    await session.commit()
    return model


async def read_messages(session: AsyncSession, conversation: Conversation) -> list[Message]:
    """지금 보고 있는 가지의 말들. 첫 말부터."""
    return await repository.active_path(session, conversation.active_leaf_id)


async def delete_conversation(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> None:
    """대화를 지운다(지운 시각을 적는다). 없으면 ConversationNotFoundError."""
    conversation, _, _ = await get_conversation(session, viewer, conversation_id)
    conversation.deleted_at = func.now()
    await session.commit()


def is_generating(conversation: Conversation, now: datetime) -> bool:
    """대화가 지금 답을 쓰는 중인가. 차례를 쥔 지 GENERATION_STALE 이 지났으면 아니다(서버가 꺼졌다)."""
    since = conversation.generating_since
    return since is not None and since >= now - GENERATION_STALE


async def message_alternatives(
    session: AsyncSession, conversation: Conversation, messages: list[Message]
) -> dict[uuid.UUID | None, list[uuid.UUID]]:
    """지금 가지의 말마다 그 대안들(같은 부모 아래의 말들). 부모로 찾는다."""
    if not messages:
        return {}
    return await repository.alternatives(session, conversation.id, [message.parent_id for message in messages])


async def choose_branch(
    session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, message_id: uuid.UUID, now: datetime
) -> None:
    """
    그 말의 가지를 본다(다른 대안을 고른다). 가지의 끝은 그 말 아래에서 가장 나중에 생긴 말이다.

    대화가 없으면 ConversationNotFoundError, 그 대화의 말이 아니면 MessageNotFoundError,
    답을 쓰는 중이면 ConversationBusyError. 수정 시각은 바꾸지 않는다.
    """
    conversation, _, _ = await get_conversation(session, viewer, conversation_id)
    message = await session.get(Message, message_id)
    if message is None or message.conversation_id != conversation.id:
        raise MessageNotFoundError
    leaf_id = await repository.latest_descendant(session, message.id)
    if not await repository.set_leaf(session, conversation.id, leaf_id, now - GENERATION_STALE):
        raise ConversationBusyError
    await session.commit()


async def edit_message(
    session: AsyncSession, viewer: Viewer, message_id: uuid.UUID, content: str, now: datetime
) -> Message:
    """
    캐릭터의 말을 그 자리에서 고친다(상대의 말 고치기). 호출이 아니라 청구하지 않는다. 고친 말을 돌려준다.

    말이 없으면 MessageNotFoundError, 사람의 말이면 NotEditableError, 답을 쓰는 중이면 ConversationBusyError.
    다음 호출부터 고친 글이 모델에 간다. 대화의 수정 시각(목록의 차례)은 바꾸지 않는다.
    """
    found = await repository.find_visible_message(
        session, viewer.claims.user_id, allowed_ratings(viewer.claims), message_id
    )
    if found is None:
        raise MessageNotFoundError
    message, _ = found
    if message.role != Role.ASSISTANT:
        raise NotEditableError
    if not await repository.edit_message(session, message.id, content, now - GENERATION_STALE):
        raise ConversationBusyError
    await session.commit()
    await session.refresh(message)
    return message
