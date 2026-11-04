# trpg-server/app/banners/service.py

"""
홍보 배너(#994)의 규칙. 운영자가 공개 중인 시나리오만 건다. 보는 사람에게는 지금 기간 안이고 볼 수 있는 것만 낸다.
링크로만 여는 시나리오(#993)와 보는 사람이 거른 것(성인 작품 숨김 #986, 성향 #987)은 공개 목록처럼 빠진다.

거는 때만 "공개 중"을 본다. 그 뒤에 공개를 내리거나 지우면 배너는 남지만 보이지 않는다(읽을 때 거른다).
다시 공개하면 기간 안이면 다시 보인다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from server_core.auth.tokens import AccessClaims
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.ratings import allowed_ratings
from app.banners import repository
from app.banners.models import Banner
from app.banners.schemas import BannerCreate, BannerUpdate, require_order
from app.listings.repository import ListingFilter, PublicRow


class BannerNotFoundError(Exception):
    """그런 배너가 없다. 404 다."""


class ScenarioNotPublishedError(Exception):
    """공개 중인 시나리오가 아니다(없거나, 지웠거나, 공개하지 않았다). 409 다."""


@dataclass(frozen=True)
class BannerView:
    """운영자가 보는 배너 하나."""

    banner: Banner
    title: str
    shown: bool


async def list_shown(
    session: AsyncSession, viewer: AccessClaims | None, where: ListingFilter, now: datetime
) -> list[tuple[Banner, PublicRow]]:
    """지금 걸린 배너. 보는 사람(로그인하지 않았으면 None)이 볼 수 있는 등급만이고, 그 사람의 설정(where)으로 거른다."""
    return await repository.list_shown(session, allowed_ratings(viewer), where, now)


async def list_for_operator(session: AsyncSession, now: datetime) -> list[BannerView]:
    """모든 배너와 지금 보이는지."""
    shown = await repository.shown_ids(session, now)
    return [BannerView(banner, title, banner.id in shown) for banner, title in await repository.list_all(session)]


async def create_banner(session: AsyncSession, operator_id: uuid.UUID, data: BannerCreate, now: datetime) -> BannerView:
    """공개 중인 시나리오의 배너를 건다. 시작을 비우면 지금부터다. 아니면 ScenarioNotPublishedError."""
    title = await repository.find_title_if_published(session, data.scenario_id)
    if title is None:
        raise ScenarioNotPublishedError
    starts_at = data.starts_at or now
    require_order(starts_at, data.ends_at)
    banner = Banner(
        scenario_id=data.scenario_id,
        position=data.position,
        starts_at=starts_at,
        ends_at=data.ends_at,
        created_by=operator_id,
    )
    repository.add_banner(session, banner)
    await session.commit()
    await session.refresh(banner)
    return await view_of(session, banner, now)


async def update_banner(session: AsyncSession, banner_id: uuid.UUID, data: BannerUpdate, now: datetime) -> BannerView:
    """배너의 차례와 기간을 고친다. 보낸 칸만 바뀐다. 없으면 BannerNotFoundError, 기간이 거꾸로면 ValueError."""
    banner = await get_banner(session, banner_id)
    changes = data.model_dump(exclude_unset=True)
    require_order(changes.get('starts_at', banner.starts_at), changes.get('ends_at', banner.ends_at))
    for field, value in changes.items():
        setattr(banner, field, value)
    await session.commit()
    await session.refresh(banner)
    return await view_of(session, banner, now)


async def delete_banner(session: AsyncSession, banner_id: uuid.UUID) -> None:
    """배너를 내린다(지운다). 없으면 BannerNotFoundError."""
    await repository.delete_banner(session, await get_banner(session, banner_id))
    await session.commit()


async def get_banner(session: AsyncSession, banner_id: uuid.UUID) -> Banner:
    """배너 하나. 없으면 BannerNotFoundError."""
    banner = await repository.find_banner(session, banner_id)
    if banner is None:
        raise BannerNotFoundError
    return banner


async def view_of(session: AsyncSession, banner: Banner, now: datetime) -> BannerView:
    """운영자에게 돌려줄 배너 하나."""
    for view in await list_for_operator(session, now):
        if view.banner.id == banner.id:
            return view
    raise BannerNotFoundError
