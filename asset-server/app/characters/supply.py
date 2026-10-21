# asset-server/app/characters/supply.py

"""
게시한 판을 다른 서버에 내주는 주소(#567). 그 서버의 서명(app/core/service_auth.py)과 사용자의 토큰을 함께 본다.

    GET /api/v1/asset/service/{caller}/characters/{id}/latest           마지막 판(번호와 문서)
    GET /api/v1/asset/service/{caller}/characters/{id}/latest/number    마지막 판의 번호만

  - 서명이 틀리면 401 이다. 토큰보다 먼저 본다(라우터의 의존성)
  - 쓸 수 있는 사람인지는 asset-server 가 판단한다(app/characters/service.py 의 get_usable_latest).
    주인이거나, 공개이고 그 판의 등급을 볼 수 있는 사람이다. 아니면 404 다.
    주인인데 등급을 쓸 수 없으면(성인 확인을 잃었다) 403 adult_content_required 다
  - 판은 바뀌지 않는다. 가져간 쪽은 시작할 때 판 하나를 복사해 고정한다
  - 번호를 묻는 길도 같은 규칙이다. 비공개로 돌렸거나 볼 수 없게 된 캐릭터는 "새 판이 있다"도 알리지 않는다
"""

import uuid

from fastapi import APIRouter, Depends, status
from server_core.auth.dependencies import CurrentUser

from app.characters import service
from app.characters.documents import CharacterDocument
from app.characters.schemas import CharacterCopy, CharacterVersionNumber
from app.core.dependencies import Session
from app.core.service_auth import verify_caller

router = APIRouter(prefix='/service/{caller}/characters', tags=['service'], dependencies=[Depends(verify_caller)])


@router.get('/{character_id}/latest', response_model=CharacterCopy, status_code=status.HTTP_200_OK)
async def copy_latest(character_id: uuid.UUID, user: CurrentUser, session: Session) -> CharacterCopy:
    """토큰의 주인이 쓸 수 있는 캐릭터의 마지막 판."""
    character, version = await service.get_usable_latest(session, user, character_id)
    return CharacterCopy(
        id=character.id,
        version=version.number,
        rating=version.rating,
        published_at=version.created_at,
        document=CharacterDocument.model_validate(version.document),
    )


@router.get('/{character_id}/latest/number', response_model=CharacterVersionNumber, status_code=status.HTTP_200_OK)
async def read_latest_number(character_id: uuid.UUID, user: CurrentUser, session: Session) -> CharacterVersionNumber:
    """토큰의 주인이 쓸 수 있는 캐릭터의 마지막 판의 번호."""
    character, version = await service.get_usable_latest(session, user, character_id)
    return CharacterVersionNumber(id=character.id, version=version.number)
