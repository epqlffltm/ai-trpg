# asset-server/app/characters/listings.py

"""
공개 캐릭터의 목록과 소개(#567). 로그인하지 않아도 읽는다(OptionalUser).

공개이고 게시한 판이 있는 캐릭터의 마지막 판을 내준다. 보는 사람이 볼 수 있는 등급만이다(app/ratings.py).
  - 로그인하지 않은 사람과 성인 확인을 하지 않은 사람은 전체 이용가만 본다.
  - 볼 수 없는 캐릭터는 없는 것과 같다(404). 403 이면 그런 캐릭터가 있다는 것이 드러난다.
토큰을 보냈는데 틀렸으면 401 이다(로그인하지 않은 것으로 넘기지 않는다, server_core 의 OptionalUser).
소개의 문서에는 업적을 싣지 않는다(조건과 숨긴 업적의 이름이 들었다). 보여도 되는 것만 따로 싣는다.
대화를 여는 chat 서버는 서비스 경로(supply.py)로 업적까지 받는다.
"""

import uuid

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser, OptionalUser

from app.characters import service
from app.characters.documents import CharacterAchievementDocument, CharacterDocument
from app.characters.models import Character, CharacterVersion
from app.characters.schemas import (
    PublicCharacterAchievement,
    PublicCharacterDetail,
    PublicCharacterPage,
    PublicCharacterSummary,
)
from app.characters.service import CharacterNotFoundError
from app.core.dependencies import Creator, ListingPreferences, Order, Paging, Search, Session
from app.hearts import service as hearts
from app.hearts.kinds import CHARACTER_HEARTS
from app.hearts.schemas import HeartState
from app.popularity import ListingOrder

router = APIRouter(prefix='/listings/characters', tags=['listings'])


def to_public_summary(character: Character, version: CharacterVersion) -> PublicCharacterSummary:
    """공개 목록의 한 줄. 마지막 판의 값이다(초안이 아니다)."""
    document = CharacterDocument.model_validate(version.document)
    return PublicCharacterSummary(
        id=character.id,
        creator_id=character.owner_id,
        version=version.number,
        name=document.name,
        tags=document.tags,
        genre=document.genre,
        rating=document.rating,
        image_id=document.image_id,
        published_at=version.created_at,
        heart_count=character.heart_count,
        start_count=character.start_count,
    )


@router.get('', response_model=PublicCharacterPage, status_code=status.HTTP_200_OK)
async def list_public(
    user: OptionalUser,
    session: Session,
    paging: Paging,
    search: Search,
    preferences: ListingPreferences,
    creator: Creator = None,
    sort: Order = ListingOrder.RECENT,
) -> PublicCharacterPage:
    """
    공개 캐릭터의 목록. 최근에 게시한 것부터다.

    검색어(q)가 "#"로 시작하면 그 태그가 붙은 것, 아니면 이름에 그 글이 들어 있는 것이다(#984).
    hide_adult, orientation 은 보는 사람의 설정이다(#986, #987, app/preferences.py). 화면이 싣는다.
    creator 를 주면 그 사람이 만든 것만이다(제작자 페이지, #992).
    sort 가 popular 면 최근 7일에 많이 시작한 것부터다(#985). 줄마다 시작한 모든 수(start_count)가 실린다.
    """
    rows, total = await service.list_public(
        session, user, search, preferences, creator, paging.limit, paging.offset, sort
    )
    return PublicCharacterPage(
        items=[to_public_summary(character, version) for character, version in rows], total=total
    )


@router.get('/hearted', response_model=PublicCharacterPage, status_code=status.HTTP_200_OK)
async def list_hearted(user: CurrentUser, session: Session, paging: Paging) -> PublicCharacterPage:
    """
    내가 관심(하트)을 둔 캐릭터(#989). 최근에 둔 것부터다.

    지금 열 수 있는 것만 나온다(비공개로 돌렸거나 숨긴 것, 볼 수 없는 등급은 빠진다). 링크 공개도 나온다.
    """
    rows, total = await hearts.list_mine(session, CHARACTER_HEARTS, user, paging.limit, paging.offset)
    return PublicCharacterPage(
        items=[to_public_summary(character, version) for character, version in rows], total=total
    )


@router.get('/{character_id}/heart', response_model=HeartState, status_code=status.HTTP_200_OK)
async def read_heart(character_id: uuid.UUID, user: CurrentUser, session: Session) -> HeartState:
    """내가 관심을 두었는지와 관심의 수(#989). 열 수 없는 캐릭터이면 404 다."""
    return await hearts.state_of(session, CHARACTER_HEARTS, user, character_id, CharacterNotFoundError)


@router.put('/{character_id}/heart', response_model=HeartState, status_code=status.HTTP_200_OK)
async def put_heart(character_id: uuid.UUID, user: CurrentUser, session: Session) -> HeartState:
    """관심을 둔다(#989). 이미 두었으면 그대로다. 열 수 없는 캐릭터이면 404 다."""
    return await hearts.put_heart(session, CHARACTER_HEARTS, user, character_id, CharacterNotFoundError)


@router.delete('/{character_id}/heart', response_model=HeartState, status_code=status.HTTP_200_OK)
async def take_heart(character_id: uuid.UUID, user: CurrentUser, session: Session) -> HeartState:
    """관심을 거둔다(#989). 두지 않았거나 비공개로 돌린 것이어도 된다."""
    return await hearts.take_heart(session, CHARACTER_HEARTS, user, character_id)


def public_achievement(achievement: CharacterAchievementDocument) -> PublicCharacterAchievement:
    """소개에 보이는 업적. 숨긴 업적은 이름, 받는 법, 그림을 가린다. 조건은 싣지 않는다."""
    shown = not achievement.hidden
    return PublicCharacterAchievement(
        id=achievement.id,
        hidden=achievement.hidden,
        name=achievement.name if shown else None,
        description=achievement.description if shown else None,
        image_id=achievement.image_id if shown else None,
    )


def to_public_detail(character: Character, version: CharacterVersion) -> PublicCharacterDetail:
    """공개 캐릭터의 소개. 마지막 판의 문서에서 업적만 빼고, 보여도 되는 업적을 따로 싣는다."""
    document = CharacterDocument.model_validate(version.document)
    return PublicCharacterDetail(
        id=character.id,
        creator_id=character.owner_id,
        version=version.number,
        published_at=version.created_at,
        document=document.model_copy(update={'achievements': []}),
        heart_count=character.heart_count,
        start_count=character.start_count,
        achievements=[public_achievement(achievement) for achievement in document.achievements],
    )


@router.get('/{character_id}', response_model=PublicCharacterDetail, status_code=status.HTTP_200_OK)
async def read_public(character_id: uuid.UUID, user: OptionalUser, session: Session) -> PublicCharacterDetail:
    """공개 캐릭터 하나. 마지막 판의 문서다."""
    character, version = await service.get_public(session, user, character_id)
    return to_public_detail(character, version)
