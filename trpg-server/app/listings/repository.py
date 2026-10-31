# trpg-server/app/listings/repository.py

"""
공개 정보를 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

읽는 길이 둘이다.
  - 제작자의 길: 시나리오의 ID 로 찾는다. 그 시나리오가 자기 것인지는 서비스가 먼저 확인한다.
  - 공개의 길: 누구나 본다. 그래서 "보여도 되는 것"의 조건(visible)을 조회 안에 넣는다.
    공개 중이고, 시나리오가 지워지지 않았고, 보는 사람이 볼 수 있는 등급이어야 한다.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.assets.models import Asset, Rating, ScenarioVersion
from app.listings.models import Genre, Listing

# 공개된 것 하나를 보여 주는 데 필요한 것들: 공개 정보, 시나리오의 공통 부분(제목, 만든 사람), 공개 중인 판
PublicRow = tuple[Listing, Asset, ScenarioVersion]


@dataclass(frozen=True)
class ListingFilter:
    """
    목록을 거르는 조건. 비워 둔 것(None)은 거르지 않는다.

    players 는 함께 할 사람의 수다. 추천 인원(min_players ~ max_players) 안에 드는 시나리오만 고른다(#428).
    """

    genre: Genre | None = None
    tag: str | None = None
    players: int | None = None


async def find_listing(session: AsyncSession, scenario_id: uuid.UUID) -> Listing | None:
    """시나리오의 공개 정보를 찾는다. 아직 만들지 않았으면 None."""
    return await session.get(Listing, scenario_id)


def add_listing(session: AsyncSession, listing: Listing) -> None:
    """새 공개 정보를 세션에 올린다."""
    session.add(listing)


async def find_version_by_id(session: AsyncSession, version_id: uuid.UUID) -> ScenarioVersion | None:
    """판을 ID 로 찾는다."""
    return await session.get(ScenarioVersion, version_id)


def visible(allowed_ratings: list[Rating]) -> Select[PublicRow]:
    """
    남에게 보여도 되는 공개 정보를 고르는 조건. 공개의 길에서 읽는 함수들이 함께 쓴다.

    allowed_ratings 는 보는 사람이 볼 수 있는 등급이다.
    """
    return (
        select(Listing, Asset, ScenarioVersion)
        .join(Asset, Asset.id == Listing.scenario_id)
        .join(ScenarioVersion, ScenarioVersion.id == Listing.version_id)
        .where(Asset.deleted_at.is_(None), Listing.rating.in_(allowed_ratings))
    )


def filtered(query: Select[PublicRow], where: ListingFilter) -> Select[PublicRow]:
    """장르, 태그, 인원으로 거른다. 비워 둔 조건은 거르지 않는다."""
    if where.genre is not None:
        query = query.where(Listing.genre == where.genre)
    if where.tag is not None:
        query = query.where(Listing.tags.contains([where.tag]))
    if where.players is not None:
        query = query.where(Listing.min_players <= where.players, Listing.max_players >= where.players)
    return query


async def find_public(session: AsyncSession, scenario_id: uuid.UUID, allowed_ratings: list[Rating]) -> PublicRow | None:
    """공개된 시나리오 하나를 찾는다. 공개하지 않았거나, 지웠거나, 볼 수 없는 등급이면 None."""
    query = visible(allowed_ratings).where(Listing.scenario_id == scenario_id)
    row = (await session.execute(query)).first()
    return tuple(row) if row else None


async def list_public(
    session: AsyncSession,
    allowed_ratings: list[Rating],
    where: ListingFilter,
    limit: int,
    offset: int,
) -> list[PublicRow]:
    """
    공개된 시나리오를 최근에 공개한 것부터 돌려준다.

    판의 굳힌 내용(snapshot)은 읽지 않는다. 목록에는 싣지 않는 큰 문서다(하나를 볼 때만 읽는다, #428).
    """
    query = filtered(visible(allowed_ratings), where).options(defer(ScenarioVersion.snapshot))
    # 공개한 시각이 같은 것끼리의 순서도 정해 둔다. 정하지 않으면 쪽을 넘길 때 같은 것이 두 번 나오거나 빠진다
    query = query.order_by(Listing.published_at.desc(), Listing.scenario_id).limit(limit).offset(offset)
    result = await session.execute(query)
    return [tuple(row) for row in result]


async def count_public(session: AsyncSession, allowed_ratings: list[Rating], where: ListingFilter) -> int:
    """공개된 시나리오가 몇 개인지 센다."""
    query = filtered(visible(allowed_ratings), where)
    return await session.scalar(select(func.count()).select_from(query.subquery())) or 0


async def unpublish_all_owned(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """
    이 사람의 시나리오의 공개를 모두 내린다(탈퇴). 소개 페이지의 글과 시나리오, 판은 그대로 남는다.

    내리는 일은 service.unpublish 와 같다(공개 중인 판과 공개한 시각을 비운다).
    """
    owned = select(Asset.id).where(Asset.owner_id == owner_id)
    statement = (
        update(Listing)
        .where(Listing.scenario_id.in_(owned), Listing.version_id.is_not(None))
        .values(version_id=None, published_at=None)
    )
    await session.execute(statement)
