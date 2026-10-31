# asset-server/app/characters/listings.py

"""
공개 캐릭터의 목록과 소개(#567). 로그인하지 않아도 읽는다(OptionalUser).

공개이고 게시한 판이 있는 캐릭터의 마지막 판을 내준다. 보는 사람이 볼 수 있는 등급만이다(app/ratings.py).
  - 로그인하지 않은 사람과 성인 확인을 하지 않은 사람은 전체 이용가만 본다.
  - 볼 수 없는 캐릭터는 없는 것과 같다(404). 403 이면 그런 캐릭터가 있다는 것이 드러난다.
토큰을 보냈는데 틀렸으면 401 이다(로그인하지 않은 것으로 넘기지 않는다, server_core 의 OptionalUser).
"""

import uuid

from fastapi import APIRouter, status
from server_core.auth.dependencies import OptionalUser

from app.characters import service
from app.characters.documents import CharacterDocument
from app.characters.models import Character, CharacterVersion
from app.characters.schemas import PublicCharacterDetail, PublicCharacterPage, PublicCharacterSummary
from app.core.dependencies import Paging, Session

router = APIRouter(prefix='/listings/characters', tags=['listings'])


def to_public_summary(character: Character, version: CharacterVersion) -> PublicCharacterSummary:
    """공개 목록의 한 줄. 마지막 판의 값이다(초안이 아니다)."""
    document = CharacterDocument.model_validate(version.document)
    return PublicCharacterSummary(
        id=character.id,
        version=version.number,
        name=document.name,
        tags=document.tags,
        genre=document.genre,
        rating=document.rating,
        image_id=document.image_id,
        published_at=version.created_at,
    )


@router.get('', response_model=PublicCharacterPage, status_code=status.HTTP_200_OK)
async def list_public(user: OptionalUser, session: Session, paging: Paging) -> PublicCharacterPage:
    """공개 캐릭터의 목록. 최근에 게시한 것부터다."""
    rows, total = await service.list_public(session, user, paging.limit, paging.offset)
    return PublicCharacterPage(
        items=[to_public_summary(character, version) for character, version in rows], total=total
    )


@router.get('/{character_id}', response_model=PublicCharacterDetail, status_code=status.HTTP_200_OK)
async def read_public(character_id: uuid.UUID, user: OptionalUser, session: Session) -> PublicCharacterDetail:
    """공개 캐릭터 하나. 마지막 판의 문서다."""
    character, version = await service.get_public(session, user, character_id)
    return PublicCharacterDetail(
        id=character.id,
        version=version.number,
        published_at=version.created_at,
        document=CharacterDocument.model_validate(version.document),
    )
