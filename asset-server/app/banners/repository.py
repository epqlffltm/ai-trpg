# asset-server/app/banners/repository.py

"""홍보 배너(#994)를 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.banners.models import Banner, BannerKind
from app.characters import repository as characters
from app.characters.models import Character, CharacterVersion, Visibility
from app.exclusions import NO_EXCLUSIONS, Exclusions, not_excluded
from app.ratings import Rating
from app.worlds import repository as worlds
from app.worlds.models import World, WorldVersion

# 공개 목록에 나오는 판이 있는 캐릭터와 세계관(등급은 가리지 않는다)
PUBLISHED_CHARACTER = (
    (Character.visibility == Visibility.PUBLIC) & Character.hidden_at.is_(None) & Character.latest_version.is_not(None)
)
PUBLISHED_WORLD = (
    (World.visibility == Visibility.PUBLIC) & World.hidden_at.is_(None) & World.latest_version.is_not(None)
)


def in_period(now: datetime):
    """지금 기간 안인 배너의 조건."""
    return (Banner.starts_at <= now) & or_(Banner.ends_at.is_(None), Banner.ends_at > now)


def order_key(banner: Banner) -> tuple:
    """배너의 차례. 작은 것이 먼저, 같으면 먼저 건 것이 먼저다."""
    return (banner.position, banner.created_at, str(banner.id))


async def shown_characters(
    session: AsyncSession,
    ratings: Sequence[Rating],
    orientation_tag: str | None,
    now: datetime,
    excluded: Exclusions = NO_EXCLUSIONS,
) -> list[tuple[Banner, Character, CharacterVersion]]:
    """
    지금 보이는 캐릭터의 배너와 그 캐릭터, 마지막 판. 공개 목록의 조건(characters.listed)을 지킨다.

    orientation_tag 를 주면 마지막 판에 그 태그가 붙은 것만이다(성향, #987). 막은 제작자와 태그(#988)의 것은 뺀다.
    """
    query = (
        select(Banner, Character, CharacterVersion)
        .join(Character, Character.id == Banner.character_id)
        .join(CharacterVersion, characters.latest_join())
        .where(in_period(now), characters.listed(ratings))
        .where(not_excluded(excluded, Character.owner_id, CharacterVersion.document))
    )
    if orientation_tag is not None:
        query = query.where(CharacterVersion.document['tags'].contains([orientation_tag]))
    return [(banner, character, version) for banner, character, version in (await session.execute(query)).all()]


async def shown_worlds(
    session: AsyncSession,
    ratings: Sequence[Rating],
    orientation_tag: str | None,
    now: datetime,
    excluded: Exclusions = NO_EXCLUSIONS,
) -> list[tuple[Banner, World, WorldVersion]]:
    """
    지금 보이는 세계관의 배너와 그 세계관, 마지막 판. 공개 목록의 조건(worlds.listed)을 지킨다.

    orientation_tag 를 주면 마지막 판에 그 태그가 붙은 것만이다(성향, #987). 막은 제작자와 태그(#988)의 것은 뺀다.
    """
    query = (
        select(Banner, World, WorldVersion)
        .join(World, World.id == Banner.world_id)
        .join(WorldVersion, worlds.latest_join())
        .where(in_period(now), worlds.listed(ratings))
        .where(not_excluded(excluded, World.owner_id, WorldVersion.document))
    )
    if orientation_tag is not None:
        query = query.where(WorldVersion.document['tags'].contains([orientation_tag]))
    return [(banner, world, version) for banner, world, version in (await session.execute(query)).all()]


async def list_all(session: AsyncSession) -> list[tuple[Banner, str]]:
    """운영자가 보는 모든 배너와 작품의 지금 이름. 지난 것도 있다."""
    query = (
        select(Banner, Character.name, World.name)
        .outerjoin(Character, Character.id == Banner.character_id)
        .outerjoin(World, World.id == Banner.world_id)
    )
    rows = (await session.execute(query)).all()
    found = [(banner, character_name or world_name) for banner, character_name, world_name in rows]
    return sorted(found, key=lambda row: order_key(row[0]))


async def shown_ids(session: AsyncSession, now: datetime) -> set[uuid.UUID]:
    """지금 누군가에게 보이는 배너의 번호. 등급은 가리지 않는다(성인용도 성인에게는 보인다)."""
    character_banners = (
        select(Banner.id)
        .join(Character, Character.id == Banner.character_id)
        .where(in_period(now), PUBLISHED_CHARACTER)
    )
    world_banners = select(Banner.id).join(World, World.id == Banner.world_id).where(in_period(now), PUBLISHED_WORLD)
    return set(await session.scalars(character_banners.union(world_banners)))


async def find_published_name(session: AsyncSession, kind: BannerKind, target_id: uuid.UUID) -> str | None:
    """공개 목록에 나오는 작품의 이름. 비공개, 숨김, 게시한 적이 없음, 없음이면 None."""
    if kind is BannerKind.CHARACTER:
        query = select(Character.name).where(Character.id == target_id, PUBLISHED_CHARACTER)
    else:
        query = select(World.name).where(World.id == target_id, PUBLISHED_WORLD)
    return await session.scalar(query)


async def find_banner(session: AsyncSession, banner_id: uuid.UUID) -> Banner | None:
    """배너 하나. 없으면 None."""
    return await session.get(Banner, banner_id)


def add_banner(session: AsyncSession, banner: Banner) -> None:
    """새 배너를 세션에 올린다."""
    session.add(banner)


async def delete_banner(session: AsyncSession, banner: Banner) -> None:
    """배너를 지운다."""
    await session.delete(banner)
