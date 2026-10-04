# game-server/app/listings/service.py

"""
시나리오의 공개 정보를 다룬다. 소개 페이지를 고치고, 공개할 판을 정하고, 공개된 것을 보여 준다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.

두 부류의 사람이 쓴다.
  - 제작자: 자기 시나리오의 공개 정보를 고친다. 시나리오가 자기 것인지부터 확인한다.
  - 다른 사용자: 공개된 것을 본다. 볼 수 있는 등급만 본다.
"""

import enum
import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.models import Rating, Scenario, ScenarioVersion
from app.assets.scenarios import repository as versions
from app.assets.service import AssetNotFoundError
from app.auth.tokens import AccessClaims
from app.listings import repository
from app.listings.models import Genre, Listing
from app.listings.repository import PublicRow
from app.listings.schemas import ListingUpdate, PublicationUpdate


class Problem(enum.StrEnum):
    """공개할 수 없는 이유."""

    # 한줄소개가 비어 있다. 목록에 보일 글이 없다
    TAGLINE_EMPTY = 'tagline_empty'
    # 장르를 하나도 고르지 않았다. 장르로 찾을 수 없다
    GENRE_MISSING = 'genre_missing'


class ListingNotReadyError(Exception):
    """
    소개 페이지가 공개할 조건을 갖추지 못했다.

    problems 는 갖추지 못한 조건 전부다.
    """

    def __init__(self, problems: list[Problem]) -> None:
        super().__init__()
        self.problems = problems


def allowed_ratings(viewer: AccessClaims) -> list[Rating]:
    """
    보는 사람이 볼 수 있는 등급.

    지금은 누구에게나 전체 이용가만 보인다. 인증 서버에 성인 인증이 없어서, 토큰으로는 성인인지 알 수 없다.
    성인 인증이 생기면 여기서 토큰을 읽어 성인용을 더한다. 등급을 가르는 곳은 이 함수 하나다.
    """
    return [Rating.ALL]


def find_problems(listing: Listing) -> list[Problem]:
    """공개할 수 없는 이유를 전부 찾는다. 없으면 빈 목록이다."""
    problems = []
    if not listing.tagline:
        problems.append(Problem.TAGLINE_EMPTY)
    if not listing.genres:
        problems.append(Problem.GENRE_MISSING)
    return problems


def apply_changes(listing: Listing, data: ListingUpdate) -> None:
    """보낸 칸만 소개 페이지에 반영한다."""
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(listing, field, value)


def publish_version(listing: Listing, version: ScenarioVersion) -> None:
    """이 판을 공개 중인 판으로 삼는다. 등급은 판에 굳어 있는 것을 읽어 적는다."""
    listing.version_id = version.id
    listing.rating = Rating(version.snapshot['rating'])
    listing.published_at = func.now()


def unpublish(listing: Listing) -> None:
    """공개를 내린다. 소개 페이지의 글은 그대로 남는다."""
    listing.version_id = None
    listing.published_at = None


def build_empty(scenario_id: uuid.UUID) -> Listing:
    """아무것도 쓰지 않은 공개 정보를 만든다. 아직 저장하지 않는다."""
    return Listing(scenario_id=scenario_id, tagline='', description='', genres=[], tags=[], rating=Rating.ALL)


async def get_or_create(session: AsyncSession, scenario_id: uuid.UUID) -> Listing:
    """
    고칠 공개 정보를 돌려준다. 아직 없으면 빈 것을 만들어 세션에 올린다.

    공개 정보는 처음 고칠 때 생긴다. 시나리오를 만들 때 함께 만들지 않는다.
    """
    listing = await repository.find_listing(session, scenario_id)
    if listing is None:
        listing = build_empty(scenario_id)
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
    session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID, data: ListingUpdate
) -> Listing:
    """
    자기 시나리오의 소개 페이지를 고친다. 시나리오가 없으면 AssetNotFoundError.

    공개 중인 페이지를 고쳐서 조건을 못 갖추게 되면 ListingNotReadyError. 고치려면 공개를 먼저 내린다.
    시나리오를 잠그고 한다. 공개 정보가 없을 때 두 요청이 동시에 만들면 부딪힌다.
    """
    await assets.lock_owned(session, Scenario, owner_id, scenario_id)
    listing = await get_or_create(session, scenario_id)
    apply_changes(listing, data)

    if listing.version_id is not None:
        problems = find_problems(listing)
        if problems:
            raise ListingNotReadyError(problems)

    await session.commit()
    await session.refresh(listing)
    return listing


async def set_publication(
    session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID, data: PublicationUpdate
) -> Listing:
    """
    자기 시나리오의 공개할 판을 정한다. 번호를 비우면 공개를 내린다.

    시나리오나 판이 없으면 AssetNotFoundError, 소개 페이지가 조건을 못 갖췄으면 ListingNotReadyError.
    """
    await assets.lock_owned(session, Scenario, owner_id, scenario_id)
    listing = await get_or_create(session, scenario_id)

    if data.version is None:
        unpublish(listing)
    else:
        version = await versions.find_version(session, scenario_id, data.version)
        if version is None:
            raise AssetNotFoundError
        problems = find_problems(listing)
        if problems:
            raise ListingNotReadyError(problems)
        publish_version(listing, version)

    await session.commit()
    await session.refresh(listing)
    return listing


async def get_published_version(session: AsyncSession, listing: Listing) -> ScenarioVersion | None:
    """공개 중인 판을 돌려준다. 공개하지 않았으면 None."""
    if listing.version_id is None:
        return None
    return await repository.find_version_by_id(session, listing.version_id)


# --- 다른 사용자 ---


async def get_public(session: AsyncSession, viewer: AccessClaims, scenario_id: uuid.UUID) -> PublicRow:
    """
    공개된 시나리오 하나를 돌려준다. 없으면 AssetNotFoundError.

    공개하지 않은 것, 지운 것, 볼 수 없는 등급인 것도 "없다"로 답한다. 있다는 것을 알려 주지 않는다.
    """
    row = await repository.find_public(session, scenario_id, allowed_ratings(viewer))
    if row is None:
        raise AssetNotFoundError
    return row


async def list_public(
    session: AsyncSession, viewer: AccessClaims, genre: Genre | None, tag: str | None, limit: int, offset: int
) -> tuple[list[PublicRow], int]:
    """공개된 시나리오의 한 쪽과 전체 개수를 돌려준다. 보는 사람이 볼 수 있는 등급만 나온다."""
    ratings = allowed_ratings(viewer)
    rows = await repository.list_public(session, ratings, genre, tag, limit, offset)
    total = await repository.count_public(session, ratings, genre, tag)
    return rows, total
