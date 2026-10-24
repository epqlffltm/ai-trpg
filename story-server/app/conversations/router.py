# story-server/app/conversations/router.py

"""
세션 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

    POST /api/v1/story/conversations        세션 시작. 201
    GET  /api/v1/story/conversations        내 세션의 목록. ?limit=&offset=&world_id=
    GET  /api/v1/story/conversations/{id}   세션 하나(가져온 판까지)

모든 주소가 로그인을 요구한다. 남의 세션은 404 다(403 이면 그 ID 가 있다는 것이 드러난다).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.assets.client import AssetUnavailableError
from app.conversations import service
from app.conversations.models import Conversation, ImportedWorld
from app.conversations.repository import ConversationRow
from app.conversations.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationPage,
    ConversationSummary,
    WorldOut,
    WorldSummary,
)
from app.conversations.service import AdultContentRequiredError, ConversationNotFoundError, WorldNotFoundError
from app.core.dependencies import CurrentViewer, Paging, Session

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


def to_summary(conversation: Conversation, world: ImportedWorld) -> ConversationSummary:
    """세션을 목록의 한 줄로."""
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        world=to_world_summary(world),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def to_detail(row: ConversationRow) -> ConversationDetail:
    """세션 하나를 응답의 모양으로."""
    conversation, world = row
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        world=WorldOut(**to_world_summary(world).model_dump(), document=world.document),
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
    data: ConversationCreate, viewer: CurrentViewer, session: Session, request: Request
) -> ConversationDetail:
    """세션을 시작한다. 세계관의 마지막 판을 가져와 고정한다."""
    conversation_id = await service.start_conversation(session, request.app.state.asset, viewer, data.world_id)
    return to_detail(await service.get_conversation(session, viewer, conversation_id))


@router.get('', response_model=ConversationPage, status_code=status.HTTP_200_OK)
async def list_conversations(
    viewer: CurrentViewer,
    session: Session,
    paging: Paging,
    world_id: Annotated[uuid.UUID | None, Query(description='asset 서버의 세계관 id. 주면 그 세계관의 세션만')] = None,
) -> ConversationPage:
    """내 세션의 목록. 최근의 것부터다."""
    rows, total = await service.list_conversations(session, viewer, world_id, paging.limit, paging.offset)
    return ConversationPage(items=[to_summary(conversation, world) for conversation, world in rows], total=total)


@router.get('/{conversation_id}', response_model=ConversationDetail, status_code=status.HTTP_200_OK)
async def read_conversation(conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session) -> ConversationDetail:
    """세션 하나. 가져온 판까지."""
    return to_detail(await service.get_conversation(session, viewer, conversation_id))
