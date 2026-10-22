# chat-server/app/conversations/router.py

"""
대화 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

    POST   /api/v1/chat/conversations              대화 시작. 201
    GET    /api/v1/chat/conversations              내 대화의 목록. ?limit=&offset=&character_id=
    GET    /api/v1/chat/conversations/{id}         대화 하나(지금 가지의 말들까지)
    PUT    /api/v1/chat/conversations/{id}/model   대화의 모델 바꾸기
    PUT    /api/v1/chat/conversations/{id}/branch  다른 대안의 가지를 보기
    DELETE /api/v1/chat/conversations/{id}         지우기. 204

모든 주소가 로그인을 요구한다. 남의 대화는 404 다(403 이면 그 ID 가 있다는 것이 드러난다).
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.assets.client import AssetUnavailableError
from app.assets.schemas import CharacterDocument
from app.billing.prices import PriceBook
from app.billing.routing import Prices
from app.catalog.models import AiModel
from app.conversations import service
from app.conversations.models import Conversation, ConversationPersona, ImportedCharacter, Message
from app.conversations.schemas import (
    BranchChoice,
    CharacterOut,
    CharacterSummary,
    ConversationCreate,
    ConversationDetail,
    ConversationModelOut,
    ConversationPage,
    ConversationSummary,
    ModelChoice,
    PathMessageOut,
    PersonaOut,
    StartOut,
)
from app.conversations.service import (
    AdultContentRequiredError,
    CharacterNotFoundError,
    ConversationBusyError,
    ConversationNotFoundError,
    MessageNotFoundError,
    ModelUnavailableError,
    PersonaNotFoundError,
    StartNotFoundError,
)
from app.core.dependencies import CurrentViewer, Now, Paging, Session
from app.ratings import Rating

router = APIRouter(prefix='/conversations', tags=['conversations'])

# asset 서버를 쓸 수 없을 때 다시 해 볼 때까지의 시간(초). 화면이 이만큼 뒤에 다시 누르게 한다
ASSET_RETRY_AFTER_SECONDS = 5


# --- 응답의 모양으로 바꾸기 ---


def to_character_summary(character: ImportedCharacter) -> CharacterSummary:
    """판의 사본을 목록의 모양으로."""
    return CharacterSummary(
        id=character.source_id,
        version=character.version,
        name=character.name,
        image_id=character.document.get('image_id'),
        rating=character.rating,
    )


def to_model(model: AiModel, usable: bool) -> ConversationModelOut:
    """대화의 모델을 응답의 모양으로. usable 은 이 대화에 지금도 고를 수 있나다."""
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
    character: ImportedCharacter,
    models: dict[str, AiModel],
    book: PriceBook | None,
    now: datetime,
) -> ConversationModelOut | None:
    """대화가 가리키는 모델. 고르지 않았으면 None 이다. book 이 None 이면 값을 모르는 것이다(팔고 있다고 본다)."""
    model = models.get(conversation.model_slug)
    if model is None:
        return None
    return to_model(model, service.model_usable(model, Rating(character.rating), book, now))


def to_summary(
    conversation: Conversation,
    character: ImportedCharacter,
    models: dict[str, AiModel],
    book: PriceBook | None,
    now: datetime,
) -> ConversationSummary:
    """대화를 목록의 한 줄로."""
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        character=to_character_summary(character),
        model=conversation_model(conversation, character, models, book, now),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


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


def to_path_message(message: Message, alternatives: dict[uuid.UUID | None, list[uuid.UUID]]) -> PathMessageOut:
    """지금 가지의 말 하나와 그 대안들. 대안을 못 찾으면(있을 수 없다) 그 말 하나다."""
    return PathMessageOut(
        id=message.id,
        parent_id=message.parent_id,
        role=message.role,
        content=message.content,
        status=message.status,
        created_at=message.created_at,
        alternatives=alternatives.get(message.parent_id, [message.id]),
    )


def to_detail(
    row: service.ConversationRow,
    messages: list[Message],
    alternatives: dict[uuid.UUID | None, list[uuid.UUID]],
    models: dict[str, AiModel],
    book: PriceBook | None,
    now: datetime,
) -> ConversationDetail:
    """대화 하나를 응답의 모양으로."""
    conversation, character, persona = row
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        start=StartOut(title=conversation.start_title, situation=conversation.start_situation),
        character=CharacterOut(
            id=character.source_id,
            version=character.version,
            rating=character.rating,
            document=CharacterDocument.model_validate(character.document),
        ),
        persona=to_persona(persona),
        model=conversation_model(conversation, character, models, book, now),
        messages=[to_path_message(message, alternatives) for message in messages],
        generating=service.is_generating(conversation, now),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


# --- 예외를 응답으로. 앱에 한 번 등록한다(app/main.py) ---


def not_found(code: str) -> JSONResponse:
    """404. 화면이 code 로 안내를 고른다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.', 'code': code})


async def handle_conversation_not_found(request: Request, error: ConversationNotFoundError) -> JSONResponse:
    """그런 대화가 없으면 404 다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.'})


async def handle_character_not_found(request: Request, error: CharacterNotFoundError) -> JSONResponse:
    """쓸 수 있는 캐릭터가 아니면 404 다(code character_not_found)."""
    return not_found('character_not_found')


async def handle_persona_not_found(request: Request, error: PersonaNotFoundError) -> JSONResponse:
    """고른 페르소나가 없으면 404 다(code persona_not_found)."""
    return not_found('persona_not_found')


async def handle_adult_content_required(request: Request, error: AdultContentRequiredError) -> JSONResponse:
    """자기 캐릭터인데 등급을 쓸 수 없으면 403 이다. 화면이 본인인증으로 안내한다(asset 서버, 게임 서버와 같다)."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={'detail': '성인 인증을 한 사람만 이용할 수 있습니다.', 'code': 'adult_content_required'},
    )


async def handle_start_not_found(request: Request, error: StartNotFoundError) -> JSONResponse:
    """판에 그 시작 상황이 없으면 422 다. 몇 개가 있는지 알려 준다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '그런 시작 상황이 없습니다.', 'code': 'start_not_found', 'starts': error.count},
    )


async def handle_model_unavailable(request: Request, error: ModelUnavailableError) -> JSONResponse:
    """고른 모델을 이 대화에 쓸 수 없으면 422 다. 화면이 모델 목록을 다시 읽어 고르게 한다."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={'detail': '이 대화에 쓸 수 없는 모델입니다.', 'code': 'model_unavailable'},
    )


async def handle_message_not_found(request: Request, error: MessageNotFoundError) -> JSONResponse:
    """그런 말이 없으면 404 다(code message_not_found)."""
    return not_found('message_not_found')


async def handle_conversation_busy(request: Request, error: ConversationBusyError) -> JSONResponse:
    """답을 쓰는 중이면 409 다. 그 답이 끝난 뒤에 한다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '답을 쓰는 중입니다. 끝난 뒤에 해 주세요.', 'code': 'generation_in_progress'},
    )


async def handle_asset_unavailable(request: Request, error: AssetUnavailableError) -> JSONResponse:
    """asset 서버를 쓸 수 없으면 503 이다. 사용자의 잘못이 아니다. 진행 중인 대화는 사본으로 돈다."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            'detail': '지금은 대화를 시작할 수 없습니다. 잠시 후 다시 시도해 주세요.',
            'code': 'asset_unavailable',
        },
        headers={'Retry-After': str(ASSET_RETRY_AFTER_SECONDS)},
    )


# --- 주소 ---


@router.post('', response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def start_conversation(
    data: ConversationCreate, viewer: CurrentViewer, session: Session, request: Request, prices: Prices, now: Now
) -> ConversationDetail:
    """대화를 시작한다. 캐릭터의 마지막 판과 페르소나를 가져와 고정한다. 모델은 지난번 것이거나 고른 것이다."""
    conversation_id = await service.start_conversation(session, request.app.state.asset, prices, viewer, data, now)
    return await read_conversation(conversation_id, viewer, session, prices, now)


@router.get('', response_model=ConversationPage, status_code=status.HTTP_200_OK)
async def list_conversations(
    viewer: CurrentViewer,
    session: Session,
    paging: Paging,
    prices: Prices,
    now: Now,
    character_id: Annotated[
        uuid.UUID | None, Query(description='asset 서버의 캐릭터 id. 주면 그 캐릭터의 대화만')
    ] = None,
) -> ConversationPage:
    """내 대화의 목록. 최근에 말한 것부터다. 가격 목록은 DB 를 읽기 전에 받는다(바깥을 기다리며 연결을 쥐지 않는다)."""
    book = await service.known_book(prices)
    rows, total = await service.list_conversations(session, viewer, character_id, paging.limit, paging.offset)
    models = await service.conversation_models(session, [conversation for conversation, _ in rows])
    return ConversationPage(
        items=[to_summary(conversation, character, models, book, now) for conversation, character in rows],
        total=total,
    )


@router.get('/{conversation_id}', response_model=ConversationDetail, status_code=status.HTTP_200_OK)
async def read_conversation(
    conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session, prices: Prices, now: Now
) -> ConversationDetail:
    """대화 하나. 지금 보고 있는 가지의 말들까지. 가격 목록은 DB 를 읽기 전에 받는다."""
    book = await service.known_book(prices)
    row = await service.get_conversation(session, viewer, conversation_id)
    messages = await service.read_messages(session, row[0])
    alternatives = await service.message_alternatives(session, row[0], messages)
    models = await service.conversation_models(session, [row[0]])
    return to_detail(row, messages, alternatives, models, book, now)


@router.put('/{conversation_id}/model', response_model=ConversationModelOut, status_code=status.HTTP_200_OK)
async def change_model(
    conversation_id: uuid.UUID, data: ModelChoice, viewer: CurrentViewer, session: Session, prices: Prices, now: Now
) -> ConversationModelOut:
    """대화의 모델을 바꾼다. 다음 말부터 그 모델로 쓰고 그 모델의 값으로 청구한다. 바꾼 모델을 돌려준다."""
    model = await service.change_model(session, prices, viewer, conversation_id, data.model, now)
    return to_model(model, usable=True)


@router.put('/{conversation_id}/branch', response_model=ConversationDetail, status_code=status.HTTP_200_OK)
async def choose_branch(
    conversation_id: uuid.UUID, data: BranchChoice, viewer: CurrentViewer, session: Session, prices: Prices, now: Now
) -> ConversationDetail:
    """다른 대안의 가지를 본다. 그 말 아래에서 가장 나중에 생긴 말이 끝이 된다. 바뀐 대화를 돌려준다."""
    await service.choose_branch(session, viewer, conversation_id, data.message_id, now)
    return await read_conversation(conversation_id, viewer, session, prices, now)


@router.delete('/{conversation_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session) -> None:
    """대화를 지운다. 목록과 읽기에 더는 나오지 않는다."""
    await service.delete_conversation(session, viewer, conversation_id)
