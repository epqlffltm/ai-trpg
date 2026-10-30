# story-server/app/conversations/router.py

"""
세션 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

    POST /api/v1/story/conversations              세션 시작. 201
    GET  /api/v1/story/conversations              내 세션의 목록. ?limit=&offset=&world_id=
    GET  /api/v1/story/conversations/{id}         세션 하나(가져온 판과 지금 가지의 말까지)
    PUT  /api/v1/story/conversations/{id}/model   세션의 모델 바꾸기
    PUT  /api/v1/story/conversations/{id}/persona 세션의 페르소나 바꾸기(같은 것이면 새 설정으로)
    PUT  /api/v1/story/conversations/{id}/branch  다른 대안의 가지를 보기. 바뀐 세션을 돌려준다
    DELETE /api/v1/story/conversations/{id}       세션 지우기(지운 시각만 적는다). 204
    PATCH /api/v1/story/messages/{id}             답 고치기(조각마다 글만). 고친 말을 돌려준다

모든 주소가 로그인을 요구한다. 남의 세션은 404 다(403 이면 그 ID 가 있다는 것이 드러난다).
쓰기(시작과 지우기, 모델과 가지 바꾸기, 답 고치기)는 사람마다 요청 수를 센다(app/limits/).
넘으면 429 too_many_attempts 다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.assets.client import AssetUnavailableError
from app.billing.prices import PriceBook
from app.billing.routing import Prices
from app.catalog.models import AiModel
from app.conversations import service
from app.conversations.models import Conversation, ConversationPersona, ImportedWorld, Message
from app.conversations.repository import ConversationRow
from app.conversations.schemas import (
    BranchChoice,
    ConversationCreate,
    ConversationDetail,
    ConversationModelOut,
    ConversationPage,
    ConversationSummary,
    MessageEdit,
    MessageOut,
    ModelChoice,
    PathMessageOut,
    PersonaChoice,
    PersonaChoiceOut,
    PersonaOut,
    ProgressOut,
    StateOut,
    WorldSummary,
    WorldView,
)
from app.conversations.service import (
    AdultContentRequiredError,
    ConversationBusyError,
    ConversationNotFoundError,
    ModelUnavailableError,
    NotEditableError,
    PersonaNotFoundError,
    WorldNotFoundError,
)
from app.core.dependencies import CurrentViewer, Now, Paging, Session
from app.limits.routing import WRITE_LIMIT
from app.lore.indexing import LoreIndexer
from app.ratings import Rating

router = APIRouter(prefix='/conversations', tags=['conversations'])
# 답 고치기는 모델을 부르지 않는 쓰기다. 사람마다 요청 수를 센다(app/limits/)
message_router = APIRouter(prefix='/messages', tags=['conversations'], dependencies=[WRITE_LIMIT])

# asset 서버를 쓸 수 없을 때 다시 해 볼 때까지의 시간(초). 화면이 이만큼 뒤에 다시 누르게 한다
ASSET_RETRY_AFTER_SECONDS = 5


# --- 응답의 모양으로 바꾸기 ---


def genre_of(document: dict) -> str | None:
    """
    판의 장르. 형식 3 까지의 판이나 고르지 않은 판은 None 이다.
    값의 목록은 asset 서버가 지킨다. 이 서버는 글자인지만 본다(장르가 늘어도 이 서버를 고치지 않아도 된다).
    """
    genre = document.get('genre')
    return genre if isinstance(genre, str) and genre else None


def to_world_summary(world: ImportedWorld) -> WorldSummary:
    """판의 사본을 목록의 모양으로."""
    return WorldSummary(
        id=world.source_id,
        version=world.version,
        name=world.name,
        image_id=world.document.get('image_id'),
        rating=world.rating,
        genre=genre_of(world.document),
    )


def to_model(model: AiModel, usable: bool) -> ConversationModelOut:
    """세션의 모델을 응답의 모양으로. usable 은 이 세션에 지금도 고를 수 있나다."""
    return ConversationModelOut(
        slug=model.slug,
        display_name=model.display_name,
        vendor=model.vendor,
        grade=model.grade,
        retires_on=model.retires_on,
        usable=usable,
    )


def conversation_model(
    conversation: Conversation,
    world: ImportedWorld,
    models: dict[str, AiModel],
    book: PriceBook | None,
    now: datetime,
) -> ConversationModelOut | None:
    """세션이 가리키는 모델. 고르지 않았으면 None 이다. book 이 None 이면 값을 모르는 것이다(팔고 있다고 본다)."""
    model = models.get(conversation.model_slug or '')
    if model is None:
        return None
    return to_model(model, service.model_usable(model, Rating(world.rating), book, now))


def to_summary(
    conversation: Conversation,
    world: ImportedWorld,
    models: dict[str, AiModel],
    book: PriceBook | None,
    now: datetime,
    progress: ProgressOut,
) -> ConversationSummary:
    """세션을 목록의 한 줄로. progress 는 지금 가지의 끝까지 온 곳이다."""
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        world=to_world_summary(world),
        model=conversation_model(conversation, world, models, book, now),
        progress=progress,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def to_message(message: Message) -> MessageOut:
    """말 하나를 응답의 모양으로."""
    return MessageOut(
        id=message.id,
        parent_id=message.parent_id,
        role=message.role,
        content=message.content,
        status=message.status,
        segments=message.segments or [],
        cast=list(message.cast or ()),
        event_id=message.event_id,
        ending_id=message.ending_id,
        edited=message.edited,
        suggestions=list(message.suggestions or ()),
        created_at=message.created_at,
    )


def to_path_message(message: Message, alternatives: dict[uuid.UUID | None, list[uuid.UUID]]) -> PathMessageOut:
    """지금 가지의 말 하나와 그 대안들. 대안을 못 찾으면(있을 수 없다) 그 말 하나다."""
    return PathMessageOut(
        **to_message(message).model_dump(), alternatives=alternatives.get(message.parent_id, [message.id])
    )


def index_lore(indexer: LoreIndexer | None, world_id: uuid.UUID | None) -> None:
    """판의 사본의 로어북 항목을 벡터로 바꿔 두라고 맡긴다(따로 돈다). 뜻으로 찾기를 껐으면 하지 않는다."""
    if indexer is not None and world_id is not None:
        indexer.request(world_id)


def to_persona(persona: ConversationPersona | None) -> PersonaOut | None:
    """페르소나의 사본을 응답의 모양으로. 없으면 None."""
    if persona is None:
        return None
    return PersonaOut(
        id=persona.source_id,
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


def to_detail(
    row: ConversationRow,
    models: dict[str, AiModel],
    book: PriceBook | None,
    now: datetime,
    messages: list[Message],
    alternatives: dict[uuid.UUID | None, list[uuid.UUID]],
    state: StateOut,
    view: WorldView,
    persona: ConversationPersona | None,
) -> ConversationDetail:
    """
    세션 하나를 응답의 모양으로. messages 는 지금 가지의 말들, alternatives 는 부모마다의 대안들,
    state 는 그 끝의 상태, view 는 그 상태에 맞춘 세계관의 칸, persona 는 가져온 페르소나의 사본이다.
    """
    conversation, world = row
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        world=to_world_summary(world),
        model=conversation_model(conversation, world, models, book, now),
        messages=[to_path_message(message, alternatives) for message in messages],
        state=state,
        view=view,
        persona=to_persona(persona),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


# --- 예외를 응답으로. 앱에 한 번 등록한다(app/main.py) ---


async def handle_conversation_not_found(request: Request, error: ConversationNotFoundError) -> JSONResponse:
    """그런 세션이 없으면 404 다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.'})


async def handle_not_editable(request: Request, error: NotEditableError) -> JSONResponse:
    """고칠 수 없는 말이면 422 다. code 가 까닭이다(not_editable, segments_mismatch)."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '그렇게 고칠 수 없는 말입니다.', 'code': error.code},
    )


async def handle_persona_not_found(request: Request, error: PersonaNotFoundError) -> JSONResponse:
    """고른 페르소나가 없으면(남의 것도) 404 다(code persona_not_found, chat 과 같다)."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.', 'code': 'persona_not_found'}
    )


async def handle_world_not_found(request: Request, error: WorldNotFoundError) -> JSONResponse:
    """쓸 수 있는 세계관이 아니면 404 다(code world_not_found)."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.', 'code': 'world_not_found'}
    )


async def handle_adult_content_required(request: Request, error: AdultContentRequiredError) -> JSONResponse:
    """자기 세계관인데 등급을 쓸 수 없으면 403 이다. 화면이 본인인증으로 안내한다(asset 서버, chat 서버와 같다)."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={'detail': '성인 인증을 한 사람만 이용할 수 있습니다.', 'code': 'adult_content_required'},
    )


async def handle_model_unavailable(request: Request, error: ModelUnavailableError) -> JSONResponse:
    """고른 모델을 이 세션에 쓸 수 없으면 422 다. 화면이 모델 목록을 다시 읽어 고르게 한다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '이 세션에 쓸 수 없는 모델입니다.', 'code': 'model_unavailable'},
    )


async def handle_conversation_busy(request: Request, error: ConversationBusyError) -> JSONResponse:
    """답을 쓰는 중이면 409 다. 그 답이 끝난 뒤에 한다(chat 과 같다)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '답을 쓰는 중입니다. 끝난 뒤에 해 주세요.', 'code': 'generation_in_progress'},
    )


async def handle_asset_unavailable(request: Request, error: AssetUnavailableError) -> JSONResponse:
    """asset 서버를 쓸 수 없으면 503 이다. 사용자의 잘못이 아니다. 진행 중인 세션은 사본으로 돈다."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            'detail': '지금은 세션을 시작할 수 없습니다. 잠시 후 다시 시도해 주세요.',
            'code': 'asset_unavailable',
        },
        headers={'Retry-After': str(ASSET_RETRY_AFTER_SECONDS)},
    )


# --- 주소 ---


@router.post('', response_model=ConversationDetail, status_code=status.HTTP_201_CREATED, dependencies=[WRITE_LIMIT])
async def start_conversation(
    data: ConversationCreate, viewer: CurrentViewer, session: Session, request: Request, prices: Prices, now: Now
) -> ConversationDetail:
    """세션을 시작한다. 세계관의 마지막 판을 가져와 고정한다. 페르소나와 모델은 지난번 것이거나 고른 것이다."""
    conversation_id = await service.start_conversation(session, request.app.state.asset, prices, viewer, data, now)
    detail = await read_conversation(conversation_id, viewer, session, prices, now)
    index_lore(request.app.state.lore_indexer, await service.conversation_world_id(session, conversation_id))
    return detail


@router.get('', response_model=ConversationPage, status_code=status.HTTP_200_OK)
async def list_conversations(
    viewer: CurrentViewer,
    session: Session,
    paging: Paging,
    prices: Prices,
    now: Now,
    world_id: Annotated[uuid.UUID | None, Query(description='asset 서버의 세계관 id. 주면 그 세계관의 세션만')] = None,
) -> ConversationPage:
    """내 세션의 목록. 최근의 것부터다. 가격 목록은 DB 를 읽기 전에 받는다(바깥을 기다리며 연결을 쥐지 않는다)."""
    book = await service.known_book(prices)
    rows, total = await service.list_conversations(session, viewer, world_id, paging.limit, paging.offset)
    models = await service.conversation_models(session, [conversation for conversation, _ in rows])
    progresses = await service.conversation_progresses(session, rows)
    items = [
        to_summary(conversation, world, models, book, now, progresses[conversation.id]) for conversation, world in rows
    ]
    return ConversationPage(items=items, total=total)


@router.get('/{conversation_id}', response_model=ConversationDetail, status_code=status.HTTP_200_OK)
async def read_conversation(
    conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session, prices: Prices, now: Now
) -> ConversationDetail:
    """세션 하나. 가져온 판과 지금 가지의 말까지. 가격 목록은 DB 를 읽기 전에 받는다."""
    book = await service.known_book(prices)
    row = await service.get_conversation(session, viewer, conversation_id)
    models = await service.conversation_models(session, [row[0]])
    messages = await service.conversation_messages(session, row[0])
    alternatives = await service.message_alternatives(session, row[0], messages)
    state, view = await service.conversation_state(session, viewer, row[1], messages)
    persona = await service.conversation_persona(session, row[0])
    return to_detail(row, models, book, now, messages, alternatives, state, view, persona)


@router.put(
    '/{conversation_id}/model',
    response_model=ConversationModelOut,
    status_code=status.HTTP_200_OK,
    dependencies=[WRITE_LIMIT],
)
async def change_model(
    conversation_id: uuid.UUID, data: ModelChoice, viewer: CurrentViewer, session: Session, prices: Prices, now: Now
) -> ConversationModelOut:
    """세션의 모델을 바꾼다. 다음 말부터 그 모델로 쓰고 그 모델의 값으로 청구한다. 바꾼 모델을 돌려준다."""
    model = await service.change_model(session, prices, viewer, conversation_id, data.model, now)
    return to_model(model, usable=True)


@router.put(
    '/{conversation_id}/persona',
    response_model=PersonaChoiceOut,
    status_code=status.HTTP_200_OK,
    dependencies=[WRITE_LIMIT],
)
async def change_persona(
    conversation_id: uuid.UUID, data: PersonaChoice, viewer: CurrentViewer, session: Session, request: Request
) -> PersonaChoiceOut:
    """
    세션의 페르소나를 바꾼다. 다음 말부터 그 페르소나로 쓴다. 같은 id 면 asset 서버의 새 설정으로 바꾼다.
    고른 페르소나가 없으면 404 persona_not_found 이고 그대로 둔다. 바꾼 페르소나를 돌려준다.
    """
    persona = await service.change_persona(session, request.app.state.asset, viewer, conversation_id, data.persona_id)
    return PersonaChoiceOut(persona=to_persona(persona))


@router.put(
    '/{conversation_id}/branch',
    response_model=ConversationDetail,
    status_code=status.HTTP_200_OK,
    dependencies=[WRITE_LIMIT],
)
async def choose_branch(
    conversation_id: uuid.UUID, data: BranchChoice, viewer: CurrentViewer, session: Session, prices: Prices, now: Now
) -> ConversationDetail:
    """
    다른 대안의 가지를 본다. 그 말 아래에서 가장 나중에 생긴 말이 끝이 된다. 바뀐 세션(그 가지의 말과 상태)을 돌려준다.
    그 세션의 말이 아니면 404 message_not_found, 답을 쓰는 중이면 409 generation_in_progress 다.
    """
    await service.choose_branch(session, viewer, conversation_id, data.message_id, now)
    return await read_conversation(conversation_id, viewer, session, prices, now)


@router.delete('/{conversation_id}', status_code=status.HTTP_204_NO_CONTENT, dependencies=[WRITE_LIMIT])
async def delete_conversation(conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session) -> None:
    """세션을 지운다. 목록과 읽기에 더는 나오지 않는다. 없거나 남의 것이면 404 conversation_not_found 다."""
    await service.delete_conversation(session, viewer, conversation_id)


@message_router.patch('/{message_id}', response_model=MessageOut, status_code=status.HTTP_200_OK)
async def edit_message(
    message_id: uuid.UUID, data: MessageEdit, viewer: CurrentViewer, session: Session, now: Now
) -> MessageOut:
    """
    답을 그 자리에서 고친다. 조각마다 고친 글을 차례대로 보낸다. 말하는 사람은 그대로이고 고친 표시(edited)가 붙는다.
    청구하지 않는다. 답이 아니면 422 not_editable, 조각의 수가 다르면 422 segments_mismatch,
    말이 없거나 남의 것이면 404 message_not_found, 답을 쓰는 중이면 409 generation_in_progress 다.
    """
    return to_message(await service.edit_message(session, viewer, message_id, data.segments, now))
