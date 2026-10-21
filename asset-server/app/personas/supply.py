# asset-server/app/personas/supply.py

"""
계정 페르소나를 다른 서버에 내주는 주소(#565). 그 서버의 서명(app/core/service_auth.py)과 사용자의 토큰을 함께 본다.

    GET /api/v1/asset/service/{caller}/personas/{id}            사본과 revision
    GET /api/v1/asset/service/{caller}/personas/{id}/revision   지금의 revision 만

  - 서명이 틀리면 401 이다. 토큰보다 먼저 본다(라우터의 의존성)
  - 토큰의 주인의 페르소나만 내준다. 남의 것과 없는 것은 404 다(주인이 쓰는 주소와 같다)
  - 판이 없다. 가져간 쪽은 사본으로 돌고, revision 이 다르면 "새 설정으로 바꾸기"를 보인다
"""

import uuid

from fastapi import APIRouter, Depends, status
from server_core.auth.dependencies import CurrentUser

from app.core.dependencies import Session
from app.core.service_auth import verify_caller
from app.personas import service
from app.personas.schemas import PersonaCopy, PersonaRevision

router = APIRouter(prefix='/service/{caller}/personas', tags=['service'], dependencies=[Depends(verify_caller)])


@router.get('/{persona_id}', response_model=PersonaCopy, status_code=status.HTTP_200_OK)
async def copy_persona(persona_id: uuid.UUID, user: CurrentUser, session: Session) -> PersonaCopy:
    """토큰의 주인의 페르소나 하나의 사본."""
    persona = await service.get_persona(session, user.user_id, persona_id)
    return PersonaCopy.model_validate(persona, from_attributes=True)


@router.get('/{persona_id}/revision', response_model=PersonaRevision, status_code=status.HTTP_200_OK)
async def read_revision(persona_id: uuid.UUID, user: CurrentUser, session: Session) -> PersonaRevision:
    """토큰의 주인의 페르소나 하나의 지금 revision."""
    persona = await service.get_persona(session, user.user_id, persona_id)
    return PersonaRevision(id=persona.id, revision=persona.revision)
