# trpg-server/app/listings/router.py

"""
공개 정보 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소가 두 갈래다.
  - /scenarios/{id}/listing: 제작자가 자기 시나리오의 소개 페이지를 고치고 공개할 판을 정한다.
  - /listings: 누구나 공개된 시나리오를 본다. 로그인하지 않아도 전체 이용가는 본다(#530).
    로그인하지 않은 요청의 수는 프록시가 IP 마다 따로 센다(docker/nginx/templates/http.inc.template 의 anonymous).
"""

import uuid
from collections.abc import Sequence
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
from app.listings import hearts, service
from app.listings.exclusions import ExclusionsParam
from app.listings.models import TAG_MAX_LENGTH, Genre, Listing, Orientation
from app.listings.popularity import ListingOrder, start_counts
from app.listings.repository import ListingFilter, PublicRow
from app.listings.schemas import (
    HeartState,
    ListingDetail,
    ListingPregen,
    ListingUpdate,
    PublicationUpdate,
    PublicListing,
    PublicListingDetail,
    PublicListingPage,
)
from app.listings.search import SEARCH_MAX_LENGTH, SEARCH_PATTERN, parse_search
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
        unlisted=listing.unlisted,
        version=version.number if version else None,
        rating=Rating(listing.rating) if version else None,
        published_at=listing.published_at,
        updated_at=listing.updated_at,
    )


def to_listing_pregens(snapshot: Snapshot) -> list[ListingPregen]:
    """판의 프리젠들을 공개 응답으로. 이름, 설명, 숫자, 캐릭터 그림(#983)만이다. 판의 순서다."""
    return [
        ListingPregen(name=pregen.name, description=pregen.description, sheet=pregen.sheet, portrait_id=pregen.image_id)
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


def to_public(listing: Listing, asset: Asset, version: ScenarioVersion, start_count: int) -> PublicListing:
    """
    공개된 시나리오를 다른 사용자에게 보여 주는 응답으로 바꾼다. 여기 적은 칸만 나간다.

    start_count 는 연 테이블의 수다(public_items 가 한 번에 센다).
    """
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
        heart_count=listing.heart_count,
        start_count=start_count,
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
# 검색칸의 검색어(#984). "#"로 시작하면 태그, 아니면 제목과 한 줄 소개에서 찾는다(app/listings/search.py).
# 공백뿐이거나 "#" 하나뿐인 검색어는 찾을 것이 없으므로 거절한다
SearchFilter = Annotated[str | None, Query(max_length=SEARCH_MAX_LENGTH, pattern=SEARCH_PATTERN)]
# 보는 사람의 설정(#986, #987). 인증 서버의 내 정보에 있고, 화면이 읽어 싣는다. 이 서버는 인증 서버를 부르지 않는다
HideAdultFilter = Annotated[bool, Query()]
OrientationFilter = Annotated[Orientation | None, Query()]
# 만든 사람의 공개 ID(#992). 제작자 페이지가 그 사람의 공개 시나리오만 부른다
CreatorFilter = Annotated[uuid.UUID | None, Query()]


def to_filter(
    excluded: ExclusionsParam,
    genre: GenreFilter = None,
    tag: TagFilter = None,
    players: PlayersFilter = None,
    q: SearchFilter = None,
    hide_adult: HideAdultFilter = False,
    orientation: OrientationFilter = None,
    creator: CreatorFilter = None,
) -> ListingFilter:
    """주소의 거르는 값을 하나로 묶는다."""
    search = parse_search(q) if q is not None else None
    return ListingFilter(
        genre=genre,
        tag=tag,
        players=players,
        search=search,
        hide_adult=hide_adult,
        orientation=orientation,
        creator=creator,
        excluded=excluded,
    )


Filter = Annotated[ListingFilter, Depends(to_filter)]
# 목록의 차례(#985). recent(최근에 공개한 것부터, 기본) 또는 popular(최근 7일에 많이 연 것부터)
OrderParam = Annotated[ListingOrder, Query()]


async def public_items(session: AsyncSession, rows: Sequence[PublicRow]) -> list[PublicListing]:
    """공개 정보의 줄들을 응답으로 바꾼다. 연 테이블의 수를 한 번에 센다."""
    counts = await start_counts(session, [listing.scenario_id for listing, _, _ in rows])
    return [to_public(listing, asset, version, counts.get(listing.scenario_id, 0)) for listing, asset, version in rows]


@public_router.get('', response_model=PublicListingPage, status_code=status.HTTP_200_OK)
async def list_listings(
    user: OptionalUser, session: Session, paging: Paging, where: Filter, sort: OrderParam = ListingOrder.RECENT
) -> PublicListingPage:
    """
    공개된 시나리오를 최근에 공개한 것부터 돌려준다. 장르, 태그, 함께 할 인원, 검색어(q)로 거를 수 있다.

    검색어가 "#"로 시작하면 그 태그가 붙은 것, 아니면 제목이나 한 줄 소개에 그 글이 들어 있는 것이다(#984).
    hide_adult 가 참이면 성인용을 뺀다(#986). orientation 을 주면 그 성향의 태그가 붙은 것만이다(#987).
    둘 다 보는 사람의 설정이고 화면이 싣는다. creator 를 주면 그 사람이 만든 것만이다(제작자 페이지, #992).

    sort 가 popular 면 최근 7일에 테이블을 많이 연 것부터다(#985). 줄마다 연 테이블의 수(start_count)가 실린다.

    로그인하지 않아도 읽는다(#530). 그때는 전체 이용가만 나온다. 토큰을 보냈는데 틀렸으면 401 이다.
    """
    rows, total = await service.list_public(session, user, where, paging.limit, paging.offset, sort)
    return PublicListingPage(items=await public_items(session, rows), total=total)


@public_router.get('/hearted', response_model=PublicListingPage, status_code=status.HTTP_200_OK)
async def list_hearted_listings(user: CurrentUser, session: Session, paging: Paging) -> PublicListingPage:
    """
    내가 관심(하트)을 둔 시나리오(#989). 최근에 둔 것부터다.

    지금 볼 수 있는 것만 나온다(공개를 내렸거나 볼 수 없는 등급이 된 것은 빠진다). 링크 공개도 나온다.
    """
    rows, total = await hearts.list_mine(session, user, paging.limit, paging.offset)
    return PublicListingPage(items=await public_items(session, rows), total=total)


@public_router.get('/{scenario_id}/heart', response_model=HeartState, status_code=status.HTTP_200_OK)
async def read_heart(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> HeartState:
    """내가 관심을 두었는지와 관심의 수(#989). 볼 수 없는 시나리오면 404 다."""
    return await hearts.state_of(session, user, scenario_id)


@public_router.put('/{scenario_id}/heart', response_model=HeartState, status_code=status.HTTP_200_OK)
async def put_heart(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> HeartState:
    """관심을 둔다(#989). 이미 두었으면 그대로다. 볼 수 없는 시나리오면 404 다."""
    return await hearts.put_heart(session, user, scenario_id)


@public_router.delete('/{scenario_id}/heart', response_model=HeartState, status_code=status.HTTP_200_OK)
async def take_heart(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> HeartState:
    """관심을 거둔다(#989). 두지 않았거나 공개를 내린 것이어도 된다."""
    return await hearts.take_heart(session, user, scenario_id)


@public_router.get('/{scenario_id}', response_model=PublicListingDetail, status_code=status.HTTP_200_OK)
async def read_public_listing(scenario_id: uuid.UUID, user: OptionalUser, session: Session) -> PublicListingDetail:
    """
    공개된 시나리오 하나를 돌려준다. 테이블을 만들기 전에 고를 것들(스타팅, 캐릭터 방식, 프리젠, 추천 모델)이 함께 있다.

    로그인하지 않아도 읽는다(#530). 그때 성인용은 없는 것(404)이다.
    """
    (listing, asset, version), recommended = await service.get_public_detail(session, user, scenario_id)
    (public,) = await public_items(session, [(listing, asset, version)])
    return to_public_detail(public, read_snapshot(version.snapshot), recommended)
