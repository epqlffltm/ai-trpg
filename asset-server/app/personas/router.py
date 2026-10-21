# asset-server/app/personas/router.py

"""
계정 페르소나 API(#565). 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

모든 주소가 로그인을 요구한다. 자기 페르소나만 다룬다. 남의 것은 404 다(403 이면 그 ID 가 있다는 것이 드러난다).
다른 서버에 사본을 내주는 길은 app/personas/supply.py 다(그 서버의 서명과 사용자의 토큰을 함께 본다).
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser

from app.core.dependencies import AppSettings, Session
from app.personas import service
from app.personas.models import Persona
from app.personas.schemas import PersonaCreate, PersonaDetail, PersonaUpdate
from app.personas.service import PersonaLimitError, PersonaNotFoundError

router = APIRouter(prefix='/personas', tags=['personas'])


def to_detail(persona: Persona) -> PersonaDetail:
    """페르소나를 응답의 모양으로 바꾼다."""
    return PersonaDetail.model_validate(persona, from_attributes=True)


async def handle_persona_not_found(request: Request, error: PersonaNotFoundError) -> JSONResponse:
    """서비스가 "그런 페르소나가 없다"고 하면 404 로 답한다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.'})


async def handle_persona_limit(request: Request, error: PersonaLimitError) -> JSONResponse:
    """상한에 닿았으면 409 다. 화면이 code 로 안내를 고른다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': f'페르소나는 {error.limit}개까지 만들 수 있습니다.', 'code': 'persona_limit'},
    )


@router.post('', response_model=PersonaDetail, status_code=status.HTTP_201_CREATED)
async def create_persona(
    data: PersonaCreate, user: CurrentUser, session: Session, settings: AppSettings
) -> PersonaDetail:
    """페르소나를 만든다. 처음 만든 것이면 기본이다."""
    persona = await service.create_persona(session, user.user_id, data, settings.persona_max_per_owner)
    return to_detail(persona)


@router.get('', response_model=list[PersonaDetail], status_code=status.HTTP_200_OK)
async def list_personas(user: CurrentUser, session: Session) -> list[PersonaDetail]:
    """자기 페르소나 전부. 기본이 먼저, 그다음 만든 차례다."""
    return [to_detail(persona) for persona in await service.list_personas(session, user.user_id)]


@router.get('/{persona_id}', response_model=PersonaDetail, status_code=status.HTTP_200_OK)
async def read_persona(persona_id: uuid.UUID, user: CurrentUser, session: Session) -> PersonaDetail:
    """자기 페르소나 하나."""
    return to_detail(await service.get_persona(session, user.user_id, persona_id))


@router.patch('/{persona_id}', response_model=PersonaDetail, status_code=status.HTTP_200_OK)
async def update_persona(
    persona_id: uuid.UUID, data: PersonaUpdate, user: CurrentUser, session: Session
) -> PersonaDetail:
    """자기 페르소나를 고친다. 보낸 칸만 바뀐다. 내용이 바뀌면 revision 이 오른다."""
    return to_detail(await service.update_persona(session, user.user_id, persona_id, data))


@router.put('/{persona_id}/default', response_model=PersonaDetail, status_code=status.HTTP_200_OK)
async def make_default(persona_id: uuid.UUID, user: CurrentUser, session: Session) -> PersonaDetail:
    """자기 페르소나 하나를 기본으로 둔다. 다른 것은 기본에서 내린다. 이미 기본이어도 200 이다."""
    return to_detail(await service.make_default(session, user.user_id, persona_id))


@router.delete('/{persona_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(persona_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 페르소나를 지운다. 기본이었으면 가장 먼저 만든 것이 기본이 된다."""
    await service.delete_persona(session, user.user_id, persona_id)
