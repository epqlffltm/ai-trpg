# game-server/app/listings/router.py

"""
공개 정보 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소가 두 갈래다.
  - /scenarios/{id}/listing: 제작자가 자기 시나리오의 소개 페이지를 고치고 공개할 판을 정한다.
  - /listings: 누구나(로그인한 사람) 공개된 시나리오를 본다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, Rating, ScenarioVersion
from app.assets.routing import Paging, Session
from app.auth.dependencies import CurrentUser
from app.listings import service
from app.listings.models import TAG_MAX_LENGTH, Genre, Listing
from app.listings.schemas import ListingDetail, ListingUpdate, PublicationUpdate, PublicListing, PublicListingPage
from app.listings.service import ListingNotReadyError

owner_router = APIRouter(prefix='/scenarios', tags=['listings'])
public_router = APIRouter(prefix='/listings', tags=['listings'])


def to_detail(listing: Listing, version: ScenarioVersion | None) -> ListingDetail:
    """공개 정보를 제작자에게 보여 주는 응답으로 바꾼다."""
    return ListingDetail(
        scenario_id=listing.scenario_id,
        tagline=listing.tagline,
        description=listing.description,
        genres=listing.genres,
        tags=listing.tags,
        version=version.number if version else None,
        rating=Rating(listing.rating) if version else None,
        published_at=listing.published_at,
        updated_at=listing.updated_at,
    )


def to_public(listing: Listing, asset: Asset, version: ScenarioVersion) -> PublicListing:
    """공개된 시나리오를 다른 사용자에게 보여 주는 응답으로 바꾼다. 여기 적은 칸만 나간다."""
    return PublicListing(
        scenario_id=listing.scenario_id,
        creator_id=asset.owner_id,
        title=asset.title,
        tagline=listing.tagline,
        description=listing.description,
        genres=listing.genres,
        tags=listing.tags,
        rating=Rating(listing.rating),
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
    listing = await service.update_listing(session, user.user_id, scenario_id, data)
    return await to_owner_response(session, listing)


@owner_router.put('/{scenario_id}/listing/publication', response_model=ListingDetail, status_code=status.HTTP_200_OK)
async def set_publication(
    scenario_id: uuid.UUID, data: PublicationUpdate, user: CurrentUser, session: Session
) -> ListingDetail:
    """공개할 판을 정한다. 시나리오 하나에 공개 판은 하나다. version 을 null 로 보내면 공개를 내린다."""
    listing = await service.set_publication(session, user.user_id, scenario_id, data)
    return await to_owner_response(session, listing)


# --- 다른 사용자 ---

# 목록을 거르는 값. 주소의 ?genre=..&tag=.. 에서 읽는다
GenreFilter = Annotated[Genre | None, Query()]
TagFilter = Annotated[str | None, Query(min_length=1, max_length=TAG_MAX_LENGTH)]


@public_router.get('', response_model=PublicListingPage, status_code=status.HTTP_200_OK)
async def list_listings(
    user: CurrentUser, session: Session, paging: Paging, genre: GenreFilter = None, tag: TagFilter = None
) -> PublicListingPage:
    """공개된 시나리오를 최근에 공개한 것부터 돌려준다. 장르와 태그로 거를 수 있다."""
    rows, total = await service.list_public(session, user, genre, tag, paging.limit, paging.offset)
    return PublicListingPage(items=[to_public(*row) for row in rows], total=total)


@public_router.get('/{scenario_id}', response_model=PublicListing, status_code=status.HTTP_200_OK)
async def read_public_listing(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> PublicListing:
    """공개된 시나리오 하나를 돌려준다."""
    listing, asset, version = await service.get_public(session, user, scenario_id)
    return to_public(listing, asset, version)
