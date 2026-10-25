# story-server/app/conversations/router.py

"""
세션 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

    POST /api/v1/story/conversations              세션 시작. 201
    GET  /api/v1/story/conversations              내 세션의 목록. ?limit=&offset=&world_id=
    GET  /api/v1/story/conversations/{id}         세션 하나(가져온 판까지)
    PUT  /api/v1/story/conversations/{id}/model   세션의 모델 바꾸기

모든 주소가 로그인을 요구한다. 남의 세션은 404 다(403 이면 그 ID 가 있다는 것이 드러난다).
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
from app.conversations.models import Conversation, ImportedWorld
from app.conversations.repository import ConversationRow
from app.conversations.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationModelOut,
    ConversationPage,
    ConversationSummary,
    ModelChoice,
    WorldOut,
    WorldSummary,
)
from app.conversations.service import (
    AdultContentRequiredError,
    ConversationNotFoundError,
    ModelUnavailableError,
    WorldNotFoundError,
)
from app.core.dependencies import CurrentViewer, Now, Paging, Session
from app.ratings import Rating

router = APIRouter(prefix='/conversations', tags=['conversations'])

# asset 서버를 쓸 수 없을 때 다시 해 볼 때까지의 시간(초). 화면이 이만큼 뒤에 다시 누르게 한다
ASSET_RETRY_AFTER_SECONDS = 5


# --- 응답의 모양으로 바꾸기 ---


def to_world_summary(world: ImportedWorld) -> WorldSummary:
    """판의 사본을 목록의 모양으로."""
    return WorldSummary(
        id=world.source_id,
        version=world.version,
        name=world.name,
        image_id=world.document.get('image_id'),
        rating=world.rating,
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
) -> ConversationSummary:
    """세션을 목록의 한 줄로."""
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        world=to_world_summary(world),
        model=conversation_model(conversation, world, models, book, now),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def to_detail(
    row: ConversationRow, models: dict[str, AiModel], book: PriceBook | None, now: datetime
) -> ConversationDetail:
    """세션 하나를 응답의 모양으로."""
    conversation, world = row
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        world=WorldOut(**to_world_summary(world).model_dump(), document=world.document),
        model=conversation_model(conversation, world, models, book, now),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


# --- 예외를 응답으로. 앱에 한 번 등록한다(app/main.py) ---


async def handle_conversation_not_found(request: Request, error: ConversationNotFoundError) -> JSONResponse:
    """그런 세션이 없으면 404 다."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.'})


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


@router.post('', response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def start_conversation(
    data: ConversationCreate, viewer: CurrentViewer, session: Session, request: Request, prices: Prices, now: Now
) -> ConversationDetail:
    """세션을 시작한다. 세계관의 마지막 판을 가져와 고정한다. 모델은 지난번 것이거나 고른 것이다."""
    conversation_id = await service.start_conversation(session, request.app.state.asset, prices, viewer, data, now)
    return await read_conversation(conversation_id, viewer, session, prices, now)


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
    return ConversationPage(
        items=[to_summary(conversation, world, models, book, now) for conversation, world in rows], total=total
    )


@router.get('/{conversation_id}', response_model=ConversationDetail, status_code=status.HTTP_200_OK)
async def read_conversation(
    conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session, prices: Prices, now: Now
) -> ConversationDetail:
    """세션 하나. 가져온 판까지. 가격 목록은 DB 를 읽기 전에 받는다."""
    book = await service.known_book(prices)
    row = await service.get_conversation(session, viewer, conversation_id)
    models = await service.conversation_models(session, [row[0]])
    return to_detail(row, models, book, now)


@router.put('/{conversation_id}/model', response_model=ConversationModelOut, status_code=status.HTTP_200_OK)
async def change_model(
    conversation_id: uuid.UUID, data: ModelChoice, viewer: CurrentViewer, session: Session, prices: Prices, now: Now
) -> ConversationModelOut:
    """세션의 모델을 바꾼다. 다음 말부터 그 모델로 쓰고 그 모델의 값으로 청구한다. 바꾼 모델을 돌려준다."""
    model = await service.change_model(session, prices, viewer, conversation_id, data.model, now)
    return to_model(model, usable=True)
