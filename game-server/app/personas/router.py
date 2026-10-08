# game-server/app/personas/router.py

"""
보관함 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

보관함의 캐릭터를 테이블로 가져가는 주소는 따로 없다.
화면이 보관함의 캐릭터를 읽어 캐릭터를 정하는 요청(PUT /tables/{id}/character)을 채운다.
서버는 늘 하던 대로 그 테이블의 규칙과 방식으로 검사한다. 검사하는 길이 하나라서 보관함이 그 검사를 우회하지 못한다.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.assets.routing import Paging, Session
from app.auth.dependencies import CurrentUser
from app.personas import service
from app.personas.models import Persona
from app.personas.schemas import PersonaOut, PersonaPage, PersonaWrite
from app.personas.service import PersonaConflictError, PersonaNotFoundError

router = APIRouter(prefix='/personas', tags=['personas'])


def to_persona(persona: Persona) -> PersonaOut:
    """보관한 캐릭터를 응답으로 바꾼다."""
    return PersonaOut(
        id=persona.id,
        name=persona.name,
        description=persona.description,
        abilities=persona.abilities,
        rulebook_title=persona.rulebook_title,
        created_at=persona.created_at,
        updated_at=persona.updated_at,
    )


# --- 서비스의 예외를 응답으로 바꾼다. 앱에 한 번 등록한다(app/main.py) ---


async def handle_persona_not_found(request: Request, error: PersonaNotFoundError) -> JSONResponse:
    """
    "그런 캐릭터가 보관함에 없다"는 404 다.

    남의 것도 404 다. 403 을 주면 그 ID 의 캐릭터가 있다는 것이 드러난다.
    """
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.'})


async def handle_persona_conflict(request: Request, error: PersonaConflictError) -> JSONResponse:
    """ "지금 상태와 부딪힌다"는 409 다. 이유를 reason 에 싣는다. 화면이 이 값으로 안내를 고른다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '보관함의 지금 상태에서는 할 수 없습니다.', 'reason': error.reason},
    )


# --- 주소 ---


@router.post('', response_model=PersonaOut, status_code=status.HTTP_201_CREATED)
async def create_persona(data: PersonaWrite, user: CurrentUser, session: Session) -> PersonaOut:
    """보관함에 캐릭터를 만든다."""
    persona = await service.create_persona(session, user.user_id, data)
    return to_persona(persona)


@router.get('', response_model=PersonaPage, status_code=status.HTTP_200_OK)
async def list_personas(user: CurrentUser, session: Session, paging: Paging) -> PersonaPage:
    """내 보관함. 최근에 만든 것부터."""
    personas, total = await service.list_personas(session, user.user_id, paging.limit, paging.offset)
    return PersonaPage(items=[to_persona(persona) for persona in personas], total=total)


@router.get('/{persona_id}', response_model=PersonaOut, status_code=status.HTTP_200_OK)
async def read_persona(persona_id: uuid.UUID, user: CurrentUser, session: Session) -> PersonaOut:
    """보관한 캐릭터 하나."""
    persona = await service.get_persona(session, user.user_id, persona_id)
    return to_persona(persona)


@router.put('/{persona_id}', response_model=PersonaOut, status_code=status.HTTP_200_OK)
async def update_persona(persona_id: uuid.UUID, data: PersonaWrite, user: CurrentUser, session: Session) -> PersonaOut:
    """보관한 캐릭터를 고친다. 보낸 것으로 통째로 바뀐다. 가져간 테이블은 바뀌지 않는다."""
    persona = await service.update_persona(session, user.user_id, persona_id, data)
    return to_persona(persona)


@router.delete('/{persona_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(persona_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """보관한 캐릭터를 지운다. 가져간 테이블은 바뀌지 않는다."""
    await service.delete_persona(session, user.user_id, persona_id)
