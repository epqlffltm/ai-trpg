# asset-server/app/worlds/listings.py

"""
공개 세계관의 목록과 소개(story 의 D1, 첫 화면의 story 카드). 로그인하지 않아도 읽는다(OptionalUser).

공개이고 게시한 판이 있는 세계관의 마지막 판을 내준다. 보는 사람이 볼 수 있는 등급만이다(app/ratings.py).
캐릭터의 공개 목록(app/characters/listings.py)과 같은 규칙이다.
  - 로그인하지 않은 사람과 성인 확인을 하지 않은 사람은 전체 이용가만 본다.
  - 볼 수 없는 세계관은 없는 것과 같다(404). 403 이면 그런 세계관이 있다는 것이 드러난다.
토큰을 보냈는데 틀렸으면 401 이다(로그인하지 않은 것으로 넘기지 않는다, server_core 의 OptionalUser).

캐릭터와 달리 판의 문서를 통째로 내주지 않는다. 판에는 이벤트와 엔딩의 조건, 숨긴 인물이 들어 있다.
소개에 보여도 되는 것만 골라 싣는다(to_public_detail). 인물은 제작자가 고른 공개를 따른다:
보임은 이름과 그림, 실루엣은 둘 다 가리고, 숨김은 목록에서 뺀다.
"""

import uuid

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser, OptionalUser

from app.core.dependencies import Creator, ListingPreferences, Order, Paging, Search, Session
from app.hearts import service as hearts
from app.hearts.kinds import WORLD_HEARTS
from app.hearts.schemas import HeartState
from app.popularity import ListingOrder
from app.worlds import service
from app.worlds.documents import CastDocument, WorldDocument
from app.worlds.models import Reveal, World, WorldVersion
from app.worlds.schemas import PublicCastMember, PublicWorldDetail, PublicWorldPage, PublicWorldSummary
from app.worlds.service import WorldNotFoundError

router = APIRouter(prefix='/listings/worlds', tags=['listings'])


def to_public_summary(world: World, version: WorldVersion) -> PublicWorldSummary:
    """공개 목록의 한 줄. 마지막 판의 값이다(초안이 아니다)."""
    document = WorldDocument.model_validate(version.document)
    return PublicWorldSummary(
        id=world.id,
        creator_id=world.owner_id,
        version=version.number,
        name=document.name,
        tags=document.tags,
        genre=document.genre,
        rating=document.rating,
        image_id=document.image_id,
        deadline_days=document.deadline_days,
        published_at=version.created_at,
        heart_count=world.heart_count,
        start_count=world.start_count,
    )


def public_member(member: CastDocument) -> PublicCastMember | None:
    """소개에 보이는 인물. 숨김이면 None, 실루엣이면 이름과 그림을 가린다."""
    if member.reveal == Reveal.HIDDEN:
        return None
    shown = member.reveal == Reveal.SHOWN
    return PublicCastMember(
        id=member.id,
        reveal=member.reveal,
        name=member.character.name if shown else None,
        image_id=member.character.image_id if shown else None,
    )


def public_cast(document: WorldDocument) -> list[PublicCastMember]:
    """소개에 보이는 인물들. 판에 적힌 차례다."""
    members = (public_member(member) for member in document.cast)
    return [member for member in members if member is not None]


def to_public_detail(world: World, version: WorldVersion) -> PublicWorldDetail:
    """공개 세계관의 소개. 마지막 판에서 보여도 되는 것만 고른다."""
    document = WorldDocument.model_validate(version.document)
    return PublicWorldDetail(
        id=world.id,
        creator_id=world.owner_id,
        version=version.number,
        published_at=version.created_at,
        name=document.name,
        intro_html=document.intro_html,
        tags=document.tags,
        genre=document.genre,
        rating=document.rating,
        image_id=document.image_id,
        deadline_days=document.deadline_days,
        after_ending=document.after_ending,
        cast=public_cast(document),
        ending_count=sum(1 for ending in document.endings if ending.unlock),
        heart_count=world.heart_count,
        start_count=world.start_count,
    )


@router.get('', response_model=PublicWorldPage, status_code=status.HTTP_200_OK)
async def list_public(
    user: OptionalUser,
    session: Session,
    paging: Paging,
    search: Search,
    preferences: ListingPreferences,
    creator: Creator = None,
    sort: Order = ListingOrder.RECENT,
) -> PublicWorldPage:
    """
    공개 세계관의 목록. 최근에 게시한 것부터다.

    검색어(q)가 "#"로 시작하면 그 태그가 붙은 것, 아니면 이름에 그 글이 들어 있는 것이다(#984).
    hide_adult, orientation 은 보는 사람의 설정이다(#986, #987, app/preferences.py). 화면이 싣는다.
    creator 를 주면 그 사람이 만든 것만이다(제작자 페이지, #992).
    sort 가 popular 면 최근 7일에 많이 시작한 것부터다(#985). 줄마다 시작한 모든 수(start_count)가 실린다.
    """
    rows, total = await service.list_public(
        session, user, search, preferences, creator, paging.limit, paging.offset, sort
    )
    return PublicWorldPage(items=[to_public_summary(world, version) for world, version in rows], total=total)


@router.get('/hearted', response_model=PublicWorldPage, status_code=status.HTTP_200_OK)
async def list_hearted(user: CurrentUser, session: Session, paging: Paging) -> PublicWorldPage:
    """
    내가 관심(하트)을 둔 세계관(#989). 최근에 둔 것부터다.

    지금 열 수 있는 것만 나온다(비공개로 돌렸거나 숨긴 것, 볼 수 없는 등급은 빠진다). 링크 공개도 나온다.
    """
    rows, total = await hearts.list_mine(session, WORLD_HEARTS, user, paging.limit, paging.offset)
    return PublicWorldPage(items=[to_public_summary(world, version) for world, version in rows], total=total)


@router.get('/{world_id}/heart', response_model=HeartState, status_code=status.HTTP_200_OK)
async def read_heart(world_id: uuid.UUID, user: CurrentUser, session: Session) -> HeartState:
    """내가 관심을 두었는지와 관심의 수(#989). 열 수 없는 세계관이면 404 다."""
    return await hearts.state_of(session, WORLD_HEARTS, user, world_id, WorldNotFoundError)


@router.put('/{world_id}/heart', response_model=HeartState, status_code=status.HTTP_200_OK)
async def put_heart(world_id: uuid.UUID, user: CurrentUser, session: Session) -> HeartState:
    """관심을 둔다(#989). 이미 두었으면 그대로다. 열 수 없는 세계관이면 404 다."""
    return await hearts.put_heart(session, WORLD_HEARTS, user, world_id, WorldNotFoundError)


@router.delete('/{world_id}/heart', response_model=HeartState, status_code=status.HTTP_200_OK)
async def take_heart(world_id: uuid.UUID, user: CurrentUser, session: Session) -> HeartState:
    """관심을 거둔다(#989). 두지 않았거나 비공개로 돌린 것이어도 된다."""
    return await hearts.take_heart(session, WORLD_HEARTS, user, world_id)


@router.get('/{world_id}', response_model=PublicWorldDetail, status_code=status.HTTP_200_OK)
async def read_public(world_id: uuid.UUID, user: OptionalUser, session: Session) -> PublicWorldDetail:
    """공개 세계관의 소개. 볼 수 없으면 404 다."""
    world, version = await service.get_public(session, user, world_id)
    return to_public_detail(world, version)
