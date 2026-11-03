# trpg-server/app/banners/repository.py

"""홍보 배너(#994)를 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다."""

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.assets.models import Asset, Rating, ScenarioVersion
from app.banners.models import Banner
from app.listings.models import Listing
from app.listings.repository import PublicRow, visible


def in_period(now: datetime):
    """지금 기간 안인 배너의 조건."""
    return (Banner.starts_at <= now) & or_(Banner.ends_at.is_(None), Banner.ends_at > now)


async def list_shown(
    session: AsyncSession, allowed_ratings: list[Rating], now: datetime
) -> list[tuple[Banner, PublicRow]]:
    """
    지금 보이는 배너와 그 시나리오의 공개 정보. 차례(작은 것 먼저), 같으면 먼저 건 것부터다.

    시나리오는 공개 목록의 조건(visible: 공개 중, 지우지 않음, 볼 수 있는 등급)에 맞아야 한다.
    """
    query = (
        visible(allowed_ratings)
        .add_columns(Banner)
        .join(Banner, Banner.scenario_id == Listing.scenario_id)
        .where(in_period(now))
        .options(defer(ScenarioVersion.snapshot))
        .order_by(Banner.position, Banner.created_at, Banner.id)
    )
    rows = await session.execute(query)
    return [(banner, (listing, asset, version)) for listing, asset, version, banner in rows.all()]


async def list_all(session: AsyncSession) -> list[tuple[Banner, str]]:
    """운영자가 보는 모든 배너와 시나리오의 제목. 지난 것도 있다. 차례대로다."""
    query = (
        select(Banner, Asset.title)
        .join(Asset, Asset.id == Banner.scenario_id)
        .order_by(Banner.position, Banner.created_at, Banner.id)
    )
    return [(banner, title) for banner, title in (await session.execute(query)).all()]


async def shown_ids(session: AsyncSession, now: datetime) -> set[uuid.UUID]:
    """지금 누군가에게 보이는 배너의 번호. 등급은 가리지 않는다(성인용도 성인에게는 보인다)."""
    query = (
        select(Banner.id)
        .join(Listing, Listing.scenario_id == Banner.scenario_id)
        .join(Asset, Asset.id == Banner.scenario_id)
        .where(in_period(now), Listing.version_id.is_not(None), Asset.deleted_at.is_(None))
    )
    return set(await session.scalars(query))


async def find_banner(session: AsyncSession, banner_id: uuid.UUID) -> Banner | None:
    """배너 하나. 없으면 None."""
    return await session.get(Banner, banner_id)


async def find_title_if_published(session: AsyncSession, scenario_id: uuid.UUID) -> str | None:
    """공개 중이고 지우지 않은 시나리오의 제목. 아니면 None."""
    query = (
        select(Asset.title)
        .join(Listing, Listing.scenario_id == Asset.id)
        .where(Asset.id == scenario_id, Asset.deleted_at.is_(None), Listing.version_id.is_not(None))
    )
    return await session.scalar(query)


def add_banner(session: AsyncSession, banner: Banner) -> None:
    """새 배너를 세션에 올린다."""
    session.add(banner)


async def delete_banner(session: AsyncSession, banner: Banner) -> None:
    """배너를 지운다."""
    await session.delete(banner)
