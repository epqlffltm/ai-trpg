# trpg-server/app/listings/service.py

"""
시나리오의 공개 정보를 다룬다. 소개 페이지를 고치고, 공개할 판을 정하고, 공개된 것을 보여 준다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.

두 부류의 사람이 쓴다.
  - 제작자: 자기 시나리오의 공개 정보를 고친다. 시나리오가 자기 것인지부터 확인한다.
  - 다른 사용자: 공개된 것을 본다. 볼 수 있는 등급만 본다.

등급을 가르는 곳은 app/assets/ratings.py 다.
"""

import enum
import uuid
from collections.abc import Sequence

from server_core.auth.tokens import AccessClaims
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.models import Rating, Scenario, ScenarioVersion
from app.assets.ratings import ALL_AGES_ONLY, allowed_ratings, require_rating
from app.assets.scenarios import repository as versions
from app.assets.scenarios.snapshot import read_snapshot
from app.assets.service import AssetNotFoundError
from app.listings import repository
from app.listings.models import Listing
from app.listings.repository import ListingFilter, PublicRow
from app.listings.schemas import ListingUpdate, PublicationUpdate
from app.operators.publishing import require_publishable


class Problem(enum.StrEnum):
    """공개할 수 없는 이유."""

    # 한줄소개가 비어 있다. 목록에 보일 글이 없다
    TAGLINE_EMPTY = 'tagline_empty'
    # 장르를 고르지 않았다. 장르로 찾을 수 없고, 화면의 테마도 정할 수 없다
    GENRE_MISSING = 'genre_missing'


class ListingNotReadyError(Exception):
    """
    소개 페이지가 공개할 조건을 갖추지 못했다.

    problems 는 갖추지 못한 조건 전부다.
    """

    def __init__(self, problems: list[Problem]) -> None:
        super().__init__()
        self.problems = problems


def find_problems(listing: Listing) -> list[Problem]:
    """공개할 수 없는 이유를 전부 찾는다. 없으면 빈 목록이다."""
    problems = []
    if not listing.tagline:
        problems.append(Problem.TAGLINE_EMPTY)
    if listing.genre is None:
        problems.append(Problem.GENRE_MISSING)
    return problems


def apply_changes(listing: Listing, data: ListingUpdate) -> None:
    """보낸 칸만 소개 페이지에 반영한다."""
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(listing, field, value)


def publish_version(listing: Listing, version: ScenarioVersion) -> None:
    """이 판을 공개 중인 판으로 삼는다. 등급과 추천 인원은 판에 굳어 있는 것을 읽어 적는다."""
    listing.version_id = version.id
    snapshot = read_snapshot(version.snapshot)
    listing.rating = snapshot.rating
    listing.min_players = snapshot.recommended_players.min
    listing.max_players = snapshot.recommended_players.max
    listing.published_at = func.now()


def unpublish(listing: Listing) -> None:
    """공개를 내린다. 소개 페이지의 글은 그대로 남는다."""
    listing.version_id = None
    listing.published_at = None


def build_empty(scenario_id: uuid.UUID) -> Listing:
    """아무것도 쓰지 않은 공개 정보를 만든다. 아직 저장하지 않는다."""
    return Listing(scenario_id=scenario_id, tagline='', description='', genre=None, tags=[], rating=Rating.ALL)


async def start_listing(session: AsyncSession, scenario_id: uuid.UUID, data: ListingUpdate) -> Listing:
    """
    처음 쓰는 공개 정보를 만들어 세션에 올린다. 장르가 없으면 ListingNotReadyError(genre_missing).

    공개 정보는 처음 고칠 때 생긴다. 시나리오를 만들 때 함께 만들지 않는다.
    장르는 반드시 하나다. 그래서 처음 쓸 때 장르를 함께 보내야 한다. 장르 없는 행은 만들지 않는다.
    """
    listing = build_empty(scenario_id)
    apply_changes(listing, data)
    if listing.genre is None:
        raise ListingNotReadyError([Problem.GENRE_MISSING])
    repository.add_listing(session, listing)
    return listing


# --- 제작자 ---


async def get_listing(session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID) -> Listing:
    """
    자기 시나리오의 공개 정보를 돌려준다. 시나리오가 없으면 AssetNotFoundError.

    아직 만들지 않았으면 빈 것을 돌려준다. 저장하지는 않는다.
    """
    await assets.get_owned(session, Scenario, owner_id, scenario_id)
    return await repository.find_listing(session, scenario_id) or build_empty(scenario_id)


async def update_listing(
    session: AsyncSession,
    owner_id: uuid.UUID,
    scenario_id: uuid.UUID,
    data: ListingUpdate,
    allowed: Sequence[Rating] = ALL_AGES_ONLY,
) -> Listing:
    """
    자기 시나리오의 소개 페이지를 고친다. 시나리오가 없으면 AssetNotFoundError.

    처음 쓰는데 장르가 없거나, 공개 중인 페이지를 고쳐서 조건을 못 갖추게 되면 ListingNotReadyError.
    공개 중인 페이지를 비우려면 공개를 먼저 내린다.
    시나리오나 공개 중인 판이 성인용인데 allowed 에 성인용이 없으면 AdultContentRequiredError(#390).
    시나리오를 잠그고 한다. 공개 정보가 없을 때 두 요청이 동시에 만들면 부딪힌다.
    """
    scenario = await assets.lock_owned(session, Scenario, owner_id, scenario_id)
    require_rating(scenario.asset.rating, allowed)
    listing = await repository.find_listing(session, scenario_id)
    if listing is None:
        listing = await start_listing(session, scenario_id, data)
    else:
        require_rating(listing.rating, allowed)
        apply_changes(listing, data)

    if listing.version_id is not None:
        problems = find_problems(listing)
        if problems:
            raise ListingNotReadyError(problems)

    await session.commit()
    await session.refresh(listing)
    return listing


async def set_publication(
    session: AsyncSession,
    owner_id: uuid.UUID,
    scenario_id: uuid.UUID,
    data: PublicationUpdate,
    allowed: Sequence[Rating] = ALL_AGES_ONLY,
) -> Listing:
    """
    자기 시나리오의 공개할 판을 정한다. 번호를 비우면 공개를 내린다.

    시나리오나 판이 없으면 AssetNotFoundError, 소개 페이지가 조건을 못 갖췄으면 ListingNotReadyError,
    성인용 판인데 allowed 에 성인용이 없으면 AdultContentRequiredError(#390),
    운영자가 제재한 판이거나 공개 금지 중이면 PublicationRefusedError(#392, app/operators/publishing.py).
    공개를 내리는 것은 등급과 상관없이 된다. 성인용을 공개의 길에서 거두는 일이라 막을 까닭이 없다.
    """
    await assets.lock_owned(session, Scenario, owner_id, scenario_id)
    found = await repository.find_listing(session, scenario_id)
    # 아직 쓰지 않은 소개 페이지는 저장하지 않는다(장르 없는 행을 만들지 않는다). 공개하려 하면 조건을 못 갖춰 막힌다
    listing = found or build_empty(scenario_id)

    if data.version is None:
        unpublish(listing)
    else:
        version = await versions.find_version(session, scenario_id, data.version)
        if version is None:
            raise AssetNotFoundError
        require_rating(read_snapshot(version.snapshot).rating, allowed)
        await require_publishable(session, owner_id, version.id)
        problems = find_problems(listing)
        if problems:
            raise ListingNotReadyError(problems)
        publish_version(listing, version)

    await session.commit()
    if found is not None:
        await session.refresh(listing)
    return listing


async def get_published_version(session: AsyncSession, listing: Listing) -> ScenarioVersion | None:
    """공개 중인 판을 돌려준다. 공개하지 않았으면 None."""
    if listing.version_id is None:
        return None
    return await repository.find_version_by_id(session, listing.version_id)


# --- 다른 사용자 ---


async def get_public(session: AsyncSession, viewer: AccessClaims | None, scenario_id: uuid.UUID) -> PublicRow:
    """
    공개된 시나리오 하나를 돌려준다. 없으면 AssetNotFoundError.

    공개하지 않은 것, 지운 것, 볼 수 없는 등급인 것도 "없다"로 답한다. 있다는 것을 알려 주지 않는다.
    viewer 가 None 이면 로그인하지 않은 사람이다. 전체 이용가만 본다(#530).
    """
    row = await repository.find_public(session, scenario_id, allowed_ratings(viewer))
    if row is None:
        raise AssetNotFoundError
    return row


async def get_public_detail(
    session: AsyncSession, viewer: AccessClaims | None, scenario_id: uuid.UUID
) -> tuple[PublicRow, str | None]:
    """
    공개된 시나리오 하나와 그 시나리오의 추천 서술 모델을 돌려준다(#428). 없으면 AssetNotFoundError.

    추천 모델은 시나리오의 지금 값이다. 판에 굳히지 않는다(app/assets/scenarios/repository.py 의 recommended_model).
    """
    row = await get_public(session, viewer, scenario_id)
    return row, await versions.recommended_model(session, scenario_id)


async def list_public(
    session: AsyncSession, viewer: AccessClaims | None, where: ListingFilter, limit: int, offset: int
) -> tuple[list[PublicRow], int]:
    """
    공개된 시나리오의 한 쪽과 전체 개수를 돌려준다. 보는 사람이 볼 수 있는 등급만 나온다.

    viewer 가 None 이면 로그인하지 않은 사람이다. 전체 이용가만 본다(#530).
    """
    ratings = allowed_ratings(viewer)
    rows = await repository.list_public(session, ratings, where, limit, offset)
    total = await repository.count_public(session, ratings, where)
    return rows, total
