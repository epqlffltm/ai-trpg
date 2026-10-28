# story-server/app/conversations/service.py

"""
세션을 시작하고, 목록으로 내주고, 하나를 읽고, 모델을 바꾼다(docs/architecture/story.md 의 만드는 순서 1).

세션을 시작하는 길.
  1. 지난번 세션의 모델을 읽는다(사람이 고르지 않았을 때만). 읽은 뒤 트랜잭션을 닫는다
  2. asset 서버에서 세계관의 마지막 판을 가져온다. DB 연결을 쥐지 않은 채로 부른다
  3. 가져온 판의 등급을 이 서버의 규칙으로 한 번 더 본다(allowed_ratings)
  4. 모델을 정한다. 판의 등급을 알아야 해서 판을 가져온 뒤다. 고른 모델을 쓸 수 없으면 ModelUnavailableError(422),
     지난번 모델을 쓸 수 없으면 모델 없이 시작한다
  5. 판의 사본(사람마다, 판마다 하나)과 세션을 한 트랜잭션에서 저장한다
쓸 수 있는 세계관인지는 asset 서버가 판단한다(주인이거나, 공개이고 판의 등급을 볼 수 있는 사람).

모델은 고르거나 바꿀 때 한 번 본다. 모델 목록에서 고를 수 있고 결제 서버가 팔고 있어야 한다
(app/catalog/offers.py 의 is_sold). 그 뒤 꺼지거나 은퇴하거나 판매를 멈춰도 세션은 그 모델을 가리킨 채로 두고,
읽을 때 "더는 쓸 수 없다"(usable)를 함께 내준다. 몰래 다른 모델로 바꾸지 않는다(chat 과 같다).
결제 서버의 가격 목록은 받아 둔 것을 쓴다. 사람이 고른 모델은 가격 목록이 있어야 정한다(없으면 503).
지난번 모델과 읽을 때의 usable 은 가격 목록을 받지 못하면 팔고 있다고 본다. 말을 보낼 때 결제 서버가 다시 본다.

지키는 것.
  - 남의 세션은 없는 것과 같다(ConversationNotFoundError, 404). 볼 수 없는 등급의 세션도 그렇다.
  - 사본은 가져온 뒤 바뀌지 않는다. 원본이 다시 게시돼도 그 세션은 처음의 판으로 돈다.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.client import AssetAdultRequiredError, AssetClient, AssetNotFoundError
from app.assets.schemas import PersonaCopy, WorldCopy
from app.billing.price_list import PriceList, PriceListUnavailable
from app.billing.prices import PriceBook
from app.catalog import repository as catalog
from app.catalog.choice import is_choosable
from app.catalog.models import AiModel
from app.catalog.offers import is_sold
from app.conversations import repository
from app.conversations.models import Conversation, ConversationPersona, ImportedWorld, Message, Role
from app.conversations.repository import ConversationRow
from app.conversations.schemas import ConversationCreate, ProgressOut, StateOut, WorldView
from app.conversations.views import affection_shown, met_on, visited_on, world_view
from app.core.dependencies import Viewer
from app.engine.clock import day_of, slot_of
from app.engine.state import StoryState
from app.engine.world import AfterEnding, World, read_world
from app.ratings import Rating, allowed_ratings
from app.records import repository as records
from app.turns.scenes import staging
from app.turns.segments import Segment, render_segments, segment_dicts
from app.turns.states import state_on_path, state_view

# 답을 쓰는 중이라는 표시(conversations.generating_since)가 이보다 오래되면 서버가 도중에 꺼진 것으로 본다.
# 다음 말이 차례를 다시 잡고, 청구 정리가 그 홀드를 돌려준다(app/turns/settler.py). 모델을 부르는 시간의 상한보다 길다
GENERATION_STALE = timedelta(minutes=15)


class ConversationNotFoundError(Exception):
    """그런 세션이 없다. 남의 것, 볼 수 없는 등급의 것도 이것이다."""


class WorldNotFoundError(Exception):
    """asset 서버가 그 세계관을 쓸 수 없다고 했다(없다, 남의 비공개다, 게시한 적이 없다, 볼 수 없는 등급이다)."""


class PersonaNotFoundError(Exception):
    """고른 페르소나가 없다(남의 것도). 404 persona_not_found 다."""


class AdultContentRequiredError(Exception):
    """자기 세계관인데 등급을 쓸 수 없다. 화면이 본인인증으로 안내한다(403)."""


class ConversationBusyError(Exception):
    """세션이 답을 쓰는 중이다(409). 한 세션에 한 번에 하나의 생성만 받는다."""


class MessageNotFoundError(Exception):
    """그 말이 없다(남의 것, 볼 수 없는 등급의 세션의 것, 다른 세션의 것)(404). 다시 생성과 가지 고르기가 쓴다."""


class NotEditableError(Exception):
    """
    그렇게 고칠 수 없는 말이다(422). code 가 까닭이다.
    not_editable 은 답이 아니다(사람의 말과 행동 말은 고치지 않는다), segments_mismatch 는 조각의 수가 다르다.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


NOT_EDITABLE = 'not_editable'
SEGMENTS_MISMATCH = 'segments_mismatch'


class ModelUnavailableError(Exception):
    """고른 모델을 이 세션에 쓸 수 없다(없다, 꺼졌다, 은퇴했다, 성인 등급의 세션에 쓸 수 없다). 422 다."""


# --- 고르기와 만들기. DB 와 바깥을 모른다 ---


def require_usable_rating(copy: WorldCopy, viewer: Viewer) -> None:
    """가져온 판의 등급을 이 사람이 쓸 수 있는가. asset 서버가 이미 봤지만 이 서버의 규칙으로 한 번 더 본다."""
    if copy.rating not in allowed_ratings(viewer.claims):
        raise WorldNotFoundError


def build_world(owner_id: uuid.UUID, copy: WorldCopy) -> ImportedWorld:
    """판의 사본을 만든다. 문서는 받은 칸 전부다. 아직 저장하지 않는다."""
    return ImportedWorld(
        id=uuid.uuid4(),
        owner_id=owner_id,
        source_id=copy.id,
        version=copy.version,
        name=copy.document.name,
        rating=copy.rating,
        document=copy.document.model_dump(mode='json'),
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


def build_conversation(owner_id: uuid.UUID, world: ImportedWorld, model_slug: str | None) -> Conversation:
    """세션을 만든다. 제목은 세계관의 이름이다. 아직 저장하지 않는다."""
    return Conversation(id=uuid.uuid4(), owner_id=owner_id, world_id=world.id, title=world.name, model_slug=model_slug)


def model_usable(model: AiModel, rating: Rating, book: PriceBook | None, now: datetime) -> bool:
    """
    그 모델을 그 등급의 세션에 now 에 고를 수 있나. 모델 목록에서 고를 수 있고 결제 서버가 팔고 있어야 한다.

    book 이 None 이면 값을 모르는 것이다(가격 목록을 받지 못했다). 그때는 팔고 있다고 본다.
    """
    if not is_choosable(model, rating, now.date()):
        return False
    return book is None or is_sold(book, model.slug, now)


def require_usable_model(model: AiModel | None, rating: Rating, book: PriceBook | None, now: datetime) -> AiModel:
    """고른 모델. 표에 없거나 이 세션에 고를 수 없으면 ModelUnavailableError."""
    if model is None or not model_usable(model, rating, book, now):
        raise ModelUnavailableError
    return model


# --- asset 서버를 부르기 ---


async def fetch_world(asset: AssetClient, viewer: Viewer, world_id: uuid.UUID) -> WorldCopy:
    """세계관의 마지막 판. asset 서버의 404 와 403 을 이 서버의 예외로 바꾼다. 닿지 못하면 AssetUnavailableError."""
    try:
        return await asset.fetch_world(viewer.token, world_id)
    except AssetNotFoundError as error:
        raise WorldNotFoundError from error
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
    """지난번 세션의 페르소나의 사본. 지난번에 없었거나 그사이에 지워졌으면 None 이다(페르소나 없이 시작한다)."""
    try:
        return await fetch_chosen_persona(asset, viewer, persona_id)
    except PersonaNotFoundError:
        return None


async def fetch_persona(
    asset: AssetClient, viewer: Viewer, data: ConversationCreate, last: uuid.UUID | None
) -> PersonaCopy | None:
    """세션에 쓸 페르소나의 사본. 고른 것이면 꼭 있어야 하고, 지난번 것이면 없어도 된다."""
    if data.persona_chosen():
        return await fetch_chosen_persona(asset, viewer, data.persona_id)
    return await fetch_last_persona(asset, viewer, last)


# --- 저장과 읽기 ---


async def remember_model(session: AsyncSession, viewer: Viewer, data: ConversationCreate) -> str | None:
    """
    쓸 모델. 고르지 않았으면 지난번 세션의 것이다.

    읽은 뒤 트랜잭션을 닫는다. asset 서버를 부르는 동안 DB 연결을 쥐고 있지 않게 한다.
    """
    if data.model_chosen():
        return data.model
    slug = await repository.last_model(session, viewer.claims.user_id)
    await session.rollback()
    return slug


async def remember_persona(session: AsyncSession, viewer: Viewer, data: ConversationCreate) -> uuid.UUID | None:
    """
    지난번 세션의 페르소나(asset 서버의 id). 고른 것이 있으면 읽지 않는다(None).

    읽은 뒤 트랜잭션을 닫는다. asset 서버를 부르는 동안 DB 연결을 쥐고 있지 않게 한다.
    """
    if data.persona_chosen():
        return None
    source_id = await repository.last_persona_source(session, viewer.claims.user_id)
    await session.rollback()
    return source_id


async def known_book(prices: PriceList) -> PriceBook | None:
    """가격 목록. 받지 못했고 받아 둔 것도 없으면 None 이다(값을 모른다)."""
    try:
        return await prices.book()
    except PriceListUnavailable:
        return None


async def book_for_choice(prices: PriceList, data: ConversationCreate, slug: str | None) -> PriceBook | None:
    """
    세션의 모델을 정할 때 쓰는 가격 목록. 정할 모델이 없으면 부르지 않는다(None).

    사람이 고른 모델이면 꼭 받아야 한다. 받지 못하면 PriceListUnavailable(503). 값을 모르는 모델을 고르게 하지 않는다.
    지난번 모델이면 받지 못해도 시작한다(None, 팔고 있다고 본다). 결제 서버가 내려가도 세션은 시작된다.
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
    세션의 모델을 정한다. 고른 모델을 쓸 수 없으면 ModelUnavailableError 다.
    지난번 모델을 쓸 수 없으면 없이(None) 시작한다.
    """
    if slug is None:
        return None
    model = await catalog.get_model(session, slug)
    if data.model_chosen():
        return require_usable_model(model, rating, book, now).slug
    return slug if model is not None and model_usable(model, rating, book, now) else None


async def save_conversation(
    session: AsyncSession, owner_id: uuid.UUID, copy: WorldCopy, persona: PersonaCopy | None, model_slug: str | None
) -> uuid.UUID:
    """판의 사본, 세션, 페르소나의 사본을 한 번에 저장하고 세션의 id 를 돌려준다."""
    world = await repository.keep_world(session, build_world(owner_id, copy))
    conversation = build_conversation(owner_id, world, model_slug)
    repository.add(session, conversation)
    if persona is not None:
        # 세션이 먼저 저장되어야 사본이 그것을 가리킬 수 있다
        await session.flush()
        repository.add(session, build_persona(conversation.id, persona))
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
    세션을 시작하고 그 id 를 돌려준다. 실패하면 WorldNotFoundError, AdultContentRequiredError, PersonaNotFoundError,
    AssetUnavailableError, ModelUnavailableError, PriceListUnavailable.

    바깥(asset 서버, 결제 서버의 가격 목록)은 DB 의 트랜잭션을 열기 전에 부른다(기다리는 동안 연결을 쥐지 않는다).
    """
    remembered = await remember_model(session, viewer, data)
    last_persona = await remember_persona(session, viewer, data)
    copy = await fetch_world(asset, viewer, data.world_id)
    require_usable_rating(copy, viewer)
    persona = await fetch_persona(asset, viewer, data, last_persona)
    book = await book_for_choice(prices, data, remembered)
    model_slug = await pick_model(session, data, remembered, Rating(copy.rating), book, now)
    return await save_conversation(session, viewer.claims.user_id, copy, persona, model_slug)


async def conversation_world_id(session: AsyncSession, conversation_id: uuid.UUID) -> uuid.UUID | None:
    """세션이 쓰는 판의 사본의 id. 세션이 없으면 None."""
    conversation = await session.get(Conversation, conversation_id)
    return conversation.world_id if conversation is not None else None


async def conversation_persona(session: AsyncSession, conversation: Conversation) -> ConversationPersona | None:
    """세션에 가져온 페르소나의 사본. 페르소나 없이 시작했으면 None."""
    return await repository.persona_of(session, conversation.id)


async def get_conversation(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> ConversationRow:
    """이 사람의 세션 하나와 판의 사본. 없으면 ConversationNotFoundError."""
    found = await repository.find_visible(
        session, viewer.claims.user_id, allowed_ratings(viewer.claims), conversation_id
    )
    if found is None:
        raise ConversationNotFoundError
    return found


async def list_conversations(
    session: AsyncSession, viewer: Viewer, source_id: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[ConversationRow], int]:
    """이 사람의 세션의 한 쪽과 전체 개수. 볼 수 있는 등급만이다."""
    return await repository.list_visible(
        session, viewer.claims.user_id, allowed_ratings(viewer.claims), source_id, limit, offset
    )


async def conversation_messages(session: AsyncSession, conversation: Conversation) -> list[Message]:
    """세션의 지금 가지의 말들(첫 말부터). 말이 없으면 빈 목록이다."""
    return await repository.active_path(session, conversation.active_leaf_id)


async def branch_states(session: AsyncSession, messages: list[Message]) -> list[dict | None]:
    """지금 가지의 말마다 붙은 상태(JSON, 없는 말은 None). messages 는 지금 가지의 말들(첫 말부터)이다."""
    return await repository.states_on(session, [message.id for message in messages])


async def branch_state(session: AsyncSession, world: World, messages: list[Message]) -> StoryState:
    """지금 가지의 끝의 엔진의 상태."""
    return state_on_path(world, await branch_states(session, messages))


def places_on(states: list[dict | None]) -> list[str | None]:
    """가지의 말마다 붙은 상태의 장소(상태가 없는 말은 None)."""
    return [str(data['place']) if data is not None else None for data in states]


def state_out(world: World, state: StoryState, shown: frozenset[str]) -> StateOut:
    """
    상태를 응답의 모양으로. 선택지를 기다리는 이벤트가 있으면 그 장면이 부른 인물도 장면에 든다.
    호감도는 shown 의 인물 것만 싣는다.
    """
    waiting = world.event(state.choosing) if state.choosing is not None else None
    return state_view(world, state, staging(world, state, waiting).cast, shown)


async def conversation_state(
    session: AsyncSession, viewer: Viewer, imported: ImportedWorld, messages: list[Message]
) -> tuple[StateOut, WorldView]:
    """
    지금 가지의 끝의 상태와, 그 상태에 맞춘 세계관의 칸(app/conversations/views.py).
    만난 인물은 가지의 답들의 장면의 인물이고, 가 본 장소는 가지의 말에 붙은 상태들의 장소와 시작 장소다.
    본 엔딩은 이 사람의 계정의 기록과 이 가지의 엔딩이다.
    """
    world = read_world(imported.document)
    states = await branch_states(session, messages)
    state = state_on_path(world, states)
    met = met_on(message.cast or () for message in messages if message.role == Role.ASSISTANT)
    visited = visited_on(world.start_place, places_on(states))
    recorded = frozenset(
        record.ending_id for record in await records.endings_of(session, viewer.claims.user_id, imported.source_id)
    )
    shown = affection_shown(imported.document, met)
    return state_out(world, state, shown), world_view(world, imported.document, state, met, recorded, visited)


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
    상태는 말에 붙어 있으므로 가지를 바꾸면 그 가지의 상태(시각, 호감도, 본 엔딩)가 된다. 계정의 기록은 그대로다.

    세션이 없으면 ConversationNotFoundError, 그 세션의 말이 아니면 MessageNotFoundError,
    답을 쓰는 중이면 ConversationBusyError. 수정 시각은 바꾸지 않는다.
    """
    conversation, _ = await get_conversation(session, viewer, conversation_id)
    message = await session.get(Message, message_id)
    if message is None or message.conversation_id != conversation.id:
        raise MessageNotFoundError
    leaf_id = await repository.latest_descendant(session, message.id)
    if not await repository.set_leaf(session, conversation.id, leaf_id, now - GENERATION_STALE):
        raise ConversationBusyError
    await session.commit()


def edited_segments(message: Message, texts: list[str]) -> tuple[Segment, ...]:
    """
    답의 조각마다 글만 바꾼 조각들. 말하는 사람과 표정과 차례는 그대로다.
    글의 앞뒤 빈칸은 걷는다(모델의 조각과 같은 모양).
    답이 아니면 NotEditableError(not_editable), 조각의 수가 다르면 NotEditableError(segments_mismatch).
    """
    if message.role != Role.ASSISTANT:
        raise NotEditableError(NOT_EDITABLE)
    stored = message.segments or []
    if len(stored) != len(texts):
        raise NotEditableError(SEGMENTS_MISMATCH)
    return tuple(
        Segment(segment.get('speaker'), text.strip(), segment.get('expression'))
        for segment, text in zip(stored, texts, strict=True)
    )


async def edit_message(
    session: AsyncSession, viewer: Viewer, message_id: uuid.UUID, texts: list[str], now: datetime
) -> Message:
    """
    답을 그 자리에서 고친다. 조각마다 글만 바꾸고 본문(content)은 그 조각들로 다시 쓴다. 고친 말을 돌려준다.
    호출이 아니라 청구하지 않는다. 다음 호출부터 고친 글이 모델에 간다. 상태와 세션의 수정 시각은 그대로다.

    말이 없으면 MessageNotFoundError, 고칠 수 없으면 NotEditableError, 답을 쓰는 중이면 ConversationBusyError.
    """
    message = await repository.find_visible_message(
        session, viewer.claims.user_id, allowed_ratings(viewer.claims), message_id
    )
    if message is None:
        raise MessageNotFoundError
    segments = edited_segments(message, texts)
    if not await repository.edit_message(
        session, message.id, segment_dicts(segments), render_segments(segments), now - GENERATION_STALE
    ):
        raise ConversationBusyError
    await session.commit()
    await session.refresh(message)
    return message


async def conversation_models(session: AsyncSession, conversations: list[Conversation]) -> dict[str, AiModel]:
    """세션들이 가리키는 모델들. 이름표로 찾는다. 모델이 없는 세션은 들지 않는다."""
    slugs = {conversation.model_slug for conversation in conversations if conversation.model_slug is not None}
    return await catalog.models_in(session, slugs)


async def change_model(
    session: AsyncSession, prices: PriceList, viewer: Viewer, conversation_id: uuid.UUID, slug: str, now: datetime
) -> AiModel:
    """
    세션의 모델을 바꾸고 그 모델을 돌려준다. 세션이 없으면 ConversationNotFoundError,
    고를 수 없으면 ModelUnavailableError, 가격 목록을 받지 못했으면 PriceListUnavailable 이다.
    목록의 차례(최근의 것부터)는 바꾸지 않는다. 가격 목록은 DB 의 트랜잭션을 열기 전에 받는다.
    """
    book = await prices.book()
    conversation, world = await get_conversation(session, viewer, conversation_id)
    model = require_usable_model(await catalog.get_model(session, slug), Rating(world.rating), book, now)
    await repository.set_model(session, conversation.id, model.slug)
    await session.commit()
    return model


async def change_persona(
    session: AsyncSession, asset: AssetClient, viewer: Viewer, conversation_id: uuid.UUID, persona_id: uuid.UUID | None
) -> ConversationPersona | None:
    """
    세션의 페르소나를 바꾸고 바꾼 사본을 돌려준다(없이 이어 가면 None). 다음 말부터 카드의 [사용자]가 바뀐다.
    세션이 없으면 ConversationNotFoundError, 고른 페르소나가 없으면 PersonaNotFoundError(그대로 둔다),
    asset 서버를 쓸 수 없으면 AssetUnavailableError 다. 목록의 차례(최근의 것부터)는 바꾸지 않는다.

    세션을 먼저 확인하고 트랜잭션을 닫은 뒤 asset 서버를 부른다(기다리는 동안 연결을 쥐지 않는다).
    """
    conversation, _ = await get_conversation(session, viewer, conversation_id)
    conversation_id = conversation.id
    await session.rollback()
    copy = await fetch_chosen_persona(asset, viewer, persona_id)
    if copy is None:
        await repository.drop_persona(session, conversation_id)
    else:
        await repository.put_persona(session, build_persona(conversation_id, copy))
    await session.commit()
    return await repository.persona_of(session, conversation_id)


def progress_of(world: World, state: StoryState) -> ProgressOut:
    """가지의 끝의 상태를 목록의 진행으로. 엔딩의 이름은 판에서 찾는다(없으면 id 그대로)."""
    ending = world.ending(state.ending) if state.ending is not None else None
    return ProgressOut(
        day=day_of(state.minutes),
        slot=slot_of(world, state.minutes),
        deadline_days=world.deadline_days,
        ending=state.ending,
        ending_name=(ending.name or ending.id) if ending is not None else state.ending,
        epilogue=state.ending is not None and world.after_ending == AfterEnding.EPILOGUE,
    )


async def conversation_progress(
    session: AsyncSession, conversation: Conversation, imported: ImportedWorld
) -> ProgressOut:
    """
    세션 하나의 진행. 지금 가지의 말을 읽고 그 끝의 상태를 계산한다.
    상태는 말에 붙어 있어 가지를 바꾸거나 다시 생성하면 저장 없이 바뀐다.
    그래서 세션 표에 따로 적어 두지 않고 읽을 때 센다.
    """
    world = read_world(imported.document)
    messages = await repository.active_path(session, conversation.active_leaf_id)
    return progress_of(world, await branch_state(session, world, messages))


async def conversation_progresses(session: AsyncSession, rows: list[ConversationRow]) -> dict[uuid.UUID, ProgressOut]:
    """목록의 한 쪽의 세션마다의 진행. 세션마다 쿼리 둘이다(한 쪽은 limit 개까지라 상한이 있다)."""
    return {
        conversation.id: await conversation_progress(session, conversation, imported) for conversation, imported in rows
    }
