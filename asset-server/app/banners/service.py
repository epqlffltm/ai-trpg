# asset-server/app/banners/service.py

"""
홍보 배너(#994)의 규칙. 운영자가 공개 목록에 나오는 캐릭터와 세계관만 건다.
보는 사람에게는 지금 기간 안이고, 공개 목록의 조건(공개, 숨기지 않음, 볼 수 있는 등급)에 맞는 것만 낸다.

거는 때만 "공개 중"을 본다. 그 뒤에 비공개로 돌리거나 숨기면 배너는 남지만 보이지 않는다. 다시 공개하면 다시 보인다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from server_core.auth.tokens import AccessClaims
from sqlalchemy.ext.asyncio import AsyncSession

from app.banners import repository
from app.banners.models import Banner, BannerKind
from app.banners.schemas import BannerCreate, BannerUpdate, require_order
from app.characters.models import Character, CharacterVersion
from app.preferences import Preferences, shown_ratings
from app.ratings import allowed_ratings
from app.worlds.models import World, WorldVersion


class BannerNotFoundError(Exception):
    """그런 배너가 없다. 404 다."""


class TargetNotPublishedError(Exception):
    """공개 목록에 나오는 작품이 아니다(없거나, 비공개거나, 숨겼거나, 게시한 적이 없다). 409 다."""


@dataclass(frozen=True)
class ShownBanner:
    """보는 사람에게 낼 배너 하나. 둘 가운데 하나만 찬다."""

    banner: Banner
    character: tuple[Character, CharacterVersion] | None = None
    world: tuple[World, WorldVersion] | None = None


@dataclass(frozen=True)
class BannerView:
    """운영자가 보는 배너 하나."""

    banner: Banner
    name: str
    shown: bool


async def list_shown(
    session: AsyncSession, viewer: AccessClaims | None, preferences: Preferences, now: datetime
) -> list[ShownBanner]:
    """
    지금 걸린 배너. 보는 사람(로그인하지 않았으면 None)이 볼 수 있는 등급만이다.

    공개 목록처럼 보는 사람의 설정(#986, #987)으로 성인 작품을 숨기고 성향의 태그로 거른다.
    막은 제작자와 태그(#988)의 것은 뺀다.
    캐릭터와 세계관을 한 차례로 늘어놓는다(한 서버 안이라 섞어도 된다).
    """
    ratings = shown_ratings(allowed_ratings(viewer), preferences)
    tag = preferences.orientation_tag
    found = [
        ShownBanner(banner, character=(character, version))
        for banner, character, version in await repository.shown_characters(
            session, ratings, tag, now, preferences.excluded
        )
    ]
    found += [
        ShownBanner(banner, world=(world, version))
        for banner, world, version in await repository.shown_worlds(session, ratings, tag, now, preferences.excluded)
    ]
    return sorted(found, key=lambda shown: repository.order_key(shown.banner))


async def list_for_operator(session: AsyncSession, now: datetime) -> list[BannerView]:
    """모든 배너와 지금 보이는지."""
    shown = await repository.shown_ids(session, now)
    return [BannerView(banner, name, banner.id in shown) for banner, name in await repository.list_all(session)]


async def create_banner(session: AsyncSession, operator_id: uuid.UUID, data: BannerCreate, now: datetime) -> BannerView:
    """공개 목록에 나오는 작품의 배너를 건다. 시작을 비우면 지금부터다. 아니면 TargetNotPublishedError."""
    if await repository.find_published_name(session, data.kind, data.target_id) is None:
        raise TargetNotPublishedError
    starts_at = data.starts_at or now
    require_order(starts_at, data.ends_at)
    banner = Banner(
        character_id=data.target_id if data.kind is BannerKind.CHARACTER else None,
        world_id=data.target_id if data.kind is BannerKind.WORLD else None,
        position=data.position,
        starts_at=starts_at,
        ends_at=data.ends_at,
        created_by=operator_id,
    )
    repository.add_banner(session, banner)
    await session.commit()
    return await view_of(session, banner.id, now)


async def update_banner(session: AsyncSession, banner_id: uuid.UUID, data: BannerUpdate, now: datetime) -> BannerView:
    """배너의 차례와 기간을 고친다. 보낸 칸만 바뀐다. 없으면 BannerNotFoundError, 기간이 거꾸로면 ValueError."""
    banner = await get_banner(session, banner_id)
    changes = data.model_dump(exclude_unset=True)
    require_order(changes.get('starts_at', banner.starts_at), changes.get('ends_at', banner.ends_at))
    for field, value in changes.items():
        setattr(banner, field, value)
    await session.commit()
    return await view_of(session, banner_id, now)


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


async def view_of(session: AsyncSession, banner_id: uuid.UUID, now: datetime) -> BannerView:
    """운영자에게 돌려줄 배너 하나."""
    for view in await list_for_operator(session, now):
        if view.banner.id == banner_id:
            return view
    raise BannerNotFoundError
