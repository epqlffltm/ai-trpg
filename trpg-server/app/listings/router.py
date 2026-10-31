# trpg-server/app/listings/router.py

"""
공개 정보 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소가 두 갈래다.
  - /scenarios/{id}/listing: 제작자가 자기 시나리오의 소개 페이지를 고치고 공개할 판을 정한다.
  - /listings: 누구나 공개된 시나리오를 본다. 로그인하지 않아도 전체 이용가는 본다(#530).
    로그인하지 않은 요청의 수는 프록시가 IP 마다 따로 센다(docker/nginx/templates/http.inc.template 의 anonymous).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import CurrentUser, OptionalUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import TABLE_MAX_PLAYERS, Asset, Rating, ScenarioVersion
from app.assets.ratings import allowed_ratings
from app.assets.routing import Paging, Session
from app.assets.scenarios.schemas import RecommendedPlayers
from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.listings import service
from app.listings.models import TAG_MAX_LENGTH, Genre, Listing
from app.listings.repository import ListingFilter
from app.listings.schemas import (
    ListingDetail,
    ListingPregen,
    ListingUpdate,
    PublicationUpdate,
    PublicListing,
    PublicListingDetail,
    PublicListingPage,
)
from app.listings.service import ListingNotReadyError
from app.references.policy import references_allowed

owner_router = APIRouter(prefix='/scenarios', tags=['listings'])
public_router = APIRouter(prefix='/listings', tags=['listings'])


def to_detail(listing: Listing, version: ScenarioVersion | None) -> ListingDetail:
    """공개 정보를 제작자에게 보여 주는 응답으로 바꾼다."""
    return ListingDetail(
        scenario_id=listing.scenario_id,
        tagline=listing.tagline,
        description=listing.description,
        genre=listing.genre,
        tags=listing.tags,
        version=version.number if version else None,
        rating=Rating(listing.rating) if version else None,
        published_at=listing.published_at,
        updated_at=listing.updated_at,
    )


def to_listing_pregens(snapshot: Snapshot) -> list[ListingPregen]:
    """판의 프리젠들을 공개 응답으로. 이름, 설명, 숫자만이다. 판의 순서다."""
    return [
        ListingPregen(name=pregen.name, description=pregen.description, sheet=pregen.sheet)
        for pregen in snapshot.pregens
    ]


def to_public_detail(public: PublicListing, snapshot: Snapshot, recommended: str | None) -> PublicListingDetail:
    """
    공개된 시나리오 하나의 응답. 목록의 칸에 공개 중인 판의 고를 거리를 더한다. 여기 적은 칸만 나간다.

    판에는 GM 전용 글이 들어 있다. 판을 통째로 내주지 않고 칸을 하나씩 옮긴다.
    """
    return PublicListingDetail(
        **public.model_dump(),
        openings=snapshot.openings,
        character_modes=snapshot.character_modes,
        pregens=to_listing_pregens(snapshot),
        abilities=snapshot.rulebook.rules.abilities,
        recommended_narration_model=recommended,
        references_allowed=references_allowed(snapshot),
    )


def to_public(listing: Listing, asset: Asset, version: ScenarioVersion) -> PublicListing:
    """공개된 시나리오를 다른 사용자에게 보여 주는 응답으로 바꾼다. 여기 적은 칸만 나간다."""
    return PublicListing(
        scenario_id=listing.scenario_id,
        creator_id=asset.owner_id,
        title=asset.title,
        tagline=listing.tagline,
        description=listing.description,
        genre=listing.genre,
        tags=listing.tags,
        rating=Rating(listing.rating),
        recommended_players=RecommendedPlayers(min=listing.min_players, max=listing.max_players),
        version=version.number,
        version_note=version.note,
        published_at=listing.published_at,
    )


async def to_owner_response(session: AsyncSession, listing: Listing) -> ListingDetail:
    """공개 정보에 공개 중인 판을 붙여 제작자용 응답을 만든다."""
    version = await service.get_published_version(session, listing)
    return to_detail(listing, version)


async def handle_listing_not_ready(request: Request, error: ListingNotReadyError) -> JSONResponse:
    """서비스가 "공개할 조건을 갖추지 못했다"고 하면 409 로 답한다. 앱에 한 번 등록한다(app/main.py)."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '공개할 조건을 갖추지 못했습니다.', 'problems': list(error.problems)},
    )


# --- 제작자 ---


@owner_router.get('/{scenario_id}/listing', response_model=ListingDetail, status_code=status.HTTP_200_OK)
async def read_listing(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> ListingDetail:
    """자기 시나리오의 공개 정보를 돌려준다. 아직 쓰지 않았으면 빈 것을 돌려준다."""
    listing = await service.get_listing(session, user.user_id, scenario_id)
    return await to_owner_response(session, listing)


@owner_router.patch('/{scenario_id}/listing', response_model=ListingDetail, status_code=status.HTTP_200_OK)
async def update_listing(
    scenario_id: uuid.UUID, data: ListingUpdate, user: CurrentUser, session: Session
) -> ListingDetail:
    """자기 시나리오의 소개 페이지를 고친다. 보낸 칸만 바뀐다. 판을 새로 내지 않아도 된다."""
    listing = await service.update_listing(session, user.user_id, scenario_id, data, allowed_ratings(user))
    return await to_owner_response(session, listing)


@owner_router.put('/{scenario_id}/listing/publication', response_model=ListingDetail, status_code=status.HTTP_200_OK)
async def set_publication(
    scenario_id: uuid.UUID, data: PublicationUpdate, user: CurrentUser, session: Session
) -> ListingDetail:
    """공개할 판을 정한다. 시나리오 하나에 공개 판은 하나다. version 을 null 로 보내면 공개를 내린다."""
    listing = await service.set_publication(session, user.user_id, scenario_id, data, allowed_ratings(user))
    return await to_owner_response(session, listing)


# --- 다른 사용자 ---

# 목록을 거르는 값. 주소의 ?genre=..&tag=..&players=.. 에서 읽는다
GenreFilter = Annotated[Genre | None, Query()]
TagFilter = Annotated[str | None, Query(min_length=1, max_length=TAG_MAX_LENGTH)]
# 테이블의 정원보다 많은 수는 어떤 시나리오에도 맞지 않는다. 빈 목록 대신 422 로 화면의 잘못을 알린다
PlayersFilter = Annotated[int | None, Query(ge=1, le=TABLE_MAX_PLAYERS)]


def to_filter(genre: GenreFilter = None, tag: TagFilter = None, players: PlayersFilter = None) -> ListingFilter:
    """주소의 거르는 값을 하나로 묶는다."""
    return ListingFilter(genre=genre, tag=tag, players=players)


Filter = Annotated[ListingFilter, Depends(to_filter)]


@public_router.get('', response_model=PublicListingPage, status_code=status.HTTP_200_OK)
async def list_listings(user: OptionalUser, session: Session, paging: Paging, where: Filter) -> PublicListingPage:
    """
    공개된 시나리오를 최근에 공개한 것부터 돌려준다. 장르, 태그, 함께 할 인원으로 거를 수 있다.

    로그인하지 않아도 읽는다(#530). 그때는 전체 이용가만 나온다. 토큰을 보냈는데 틀렸으면 401 이다.
    """
    rows, total = await service.list_public(session, user, where, paging.limit, paging.offset)
    return PublicListingPage(items=[to_public(*row) for row in rows], total=total)


@public_router.get('/{scenario_id}', response_model=PublicListingDetail, status_code=status.HTTP_200_OK)
async def read_public_listing(scenario_id: uuid.UUID, user: OptionalUser, session: Session) -> PublicListingDetail:
    """
    공개된 시나리오 하나를 돌려준다. 테이블을 만들기 전에 고를 것들(스타팅, 캐릭터 방식, 프리젠, 추천 모델)이 함께 있다.

    로그인하지 않아도 읽는다(#530). 그때 성인용은 없는 것(404)이다.
    """
    (listing, asset, version), recommended = await service.get_public_detail(session, user, scenario_id)
    return to_public_detail(to_public(listing, asset, version), read_snapshot(version.snapshot), recommended)
