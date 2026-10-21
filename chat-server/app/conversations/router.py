# chat-server/app/conversations/router.py

"""
대화 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

    POST   /api/v1/chat/conversations         대화 시작. 201
    GET    /api/v1/chat/conversations         내 대화의 목록. ?limit=&offset=&character_id=
    GET    /api/v1/chat/conversations/{id}    대화 하나(지금 가지의 말들까지)
    DELETE /api/v1/chat/conversations/{id}    지우기. 204

모든 주소가 로그인을 요구한다. 남의 대화는 404 다(403 이면 그 ID 가 있다는 것이 드러난다).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.assets.client import AssetUnavailableError
from app.assets.schemas import CharacterDocument
from app.conversations import service
from app.conversations.models import Conversation, ConversationPersona, ImportedCharacter, Message
from app.conversations.schemas import (
    CharacterOut,
    CharacterSummary,
    ConversationCreate,
    ConversationDetail,
    ConversationPage,
    ConversationSummary,
    MessageOut,
    PersonaOut,
    StartOut,
)
from app.conversations.service import (
    AdultContentRequiredError,
    CharacterNotFoundError,
    ConversationNotFoundError,
    PersonaNotFoundError,
    StartNotFoundError,
)
from app.core.dependencies import CurrentViewer, Paging, Session

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


def to_summary(conversation: Conversation, character: ImportedCharacter) -> ConversationSummary:
    """대화를 목록의 한 줄로."""
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        character=to_character_summary(character),
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


def to_detail(row: service.ConversationRow, messages: list[Message]) -> ConversationDetail:
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
        messages=[MessageOut.model_validate(message, from_attributes=True) for message in messages],
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
    data: ConversationCreate, viewer: CurrentViewer, session: Session, request: Request
) -> ConversationDetail:
    """대화를 시작한다. 캐릭터의 마지막 판과 페르소나를 가져와 고정한다."""
    conversation_id = await service.start_conversation(session, request.app.state.asset, viewer, data)
    return await read_conversation(conversation_id, viewer, session)


@router.get('', response_model=ConversationPage, status_code=status.HTTP_200_OK)
async def list_conversations(
    viewer: CurrentViewer,
    session: Session,
    paging: Paging,
    character_id: Annotated[
        uuid.UUID | None, Query(description='asset 서버의 캐릭터 id. 주면 그 캐릭터의 대화만')
    ] = None,
) -> ConversationPage:
    """내 대화의 목록. 최근에 말한 것부터다."""
    rows, total = await service.list_conversations(session, viewer, character_id, paging.limit, paging.offset)
    return ConversationPage(
        items=[to_summary(conversation, character) for conversation, character in rows], total=total
    )


@router.get('/{conversation_id}', response_model=ConversationDetail, status_code=status.HTTP_200_OK)
async def read_conversation(conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session) -> ConversationDetail:
    """대화 하나. 지금 보고 있는 가지의 말들까지."""
    row = await service.get_conversation(session, viewer, conversation_id)
    messages = await service.read_messages(session, row[0])
    return to_detail(row, messages)


@router.delete('/{conversation_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session) -> None:
    """대화를 지운다. 목록과 읽기에 더는 나오지 않는다."""
    await service.delete_conversation(session, viewer, conversation_id)
