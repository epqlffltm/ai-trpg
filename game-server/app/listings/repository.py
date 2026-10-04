# game-server/app/listings/repository.py

"""
공개 정보를 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

읽는 길이 둘이다.
  - 제작자의 길: 시나리오의 ID 로 찾는다. 그 시나리오가 자기 것인지는 서비스가 먼저 확인한다.
  - 공개의 길: 누구나 본다. 그래서 "보여도 되는 것"의 조건(visible)을 조회 안에 넣는다.
    공개 중이고, 시나리오가 지워지지 않았고, 보는 사람이 볼 수 있는 등급이어야 한다.
"""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, Rating, ScenarioVersion
from app.listings.models import Genre, Listing

# 공개된 것 하나를 보여 주는 데 필요한 것들: 공개 정보, 시나리오의 공통 부분(제목, 만든 사람), 공개 중인 판
PublicRow = tuple[Listing, Asset, ScenarioVersion]


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


def filtered(query: Select[PublicRow], genre: Genre | None, tag: str | None) -> Select[PublicRow]:
    """장르와 태그로 거른다. 비워 두면 거르지 않는다."""
    if genre is not None:
        query = query.where(Listing.genres.contains([genre]))
    if tag is not None:
        query = query.where(Listing.tags.contains([tag]))
    return query


async def find_public(session: AsyncSession, scenario_id: uuid.UUID, allowed_ratings: list[Rating]) -> PublicRow | None:
    """공개된 시나리오 하나를 찾는다. 공개하지 않았거나, 지웠거나, 볼 수 없는 등급이면 None."""
    query = visible(allowed_ratings).where(Listing.scenario_id == scenario_id)
    row = (await session.execute(query)).first()
    return tuple(row) if row else None


async def list_public(
    session: AsyncSession,
    allowed_ratings: list[Rating],
    genre: Genre | None,
    tag: str | None,
    limit: int,
    offset: int,
) -> list[PublicRow]:
    """공개된 시나리오를 최근에 공개한 것부터 돌려준다."""
    query = filtered(visible(allowed_ratings), genre, tag)
    # 공개한 시각이 같은 것끼리의 순서도 정해 둔다. 정하지 않으면 쪽을 넘길 때 같은 것이 두 번 나오거나 빠진다
    query = query.order_by(Listing.published_at.desc(), Listing.scenario_id).limit(limit).offset(offset)
    result = await session.execute(query)
    return [tuple(row) for row in result]


async def count_public(
    session: AsyncSession, allowed_ratings: list[Rating], genre: Genre | None, tag: str | None
) -> int:
    """공개된 시나리오가 몇 개인지 센다."""
    query = filtered(visible(allowed_ratings), genre, tag)
    return await session.scalar(select(func.count()).select_from(query.subquery())) or 0
