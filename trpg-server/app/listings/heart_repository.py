# trpg-server/app/listings/heart_repository.py

"""
시나리오의 관심(하트, #989)을 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

관심의 수(listings.heart_count)는 줄을 넣고 지운 것과 같은 트랜잭션에서 하나씩 더하고 뺀다.
줄이 실제로 생기거나 지워졌을 때만 바꾼다. 두 번 눌러도, 동시에 눌러도 수가 어긋나지 않는다(기본 키가 한 번만 받는다).
"""

import uuid

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.assets.models import Rating, ScenarioVersion
from app.listings.models import Listing, ListingHeart
from app.listings.repository import PublicRow, visible


async def add_heart(session: AsyncSession, user_id: uuid.UUID, scenario_id: uuid.UUID) -> None:
    """관심을 둔다. 이미 있으면 아무것도 하지 않는다."""
    inserted = await session.scalar(
        insert(ListingHeart)
        .values(user_id=user_id, scenario_id=scenario_id)
        .on_conflict_do_nothing()
        .returning(ListingHeart.scenario_id)
    )
    if inserted is not None:
        await session.execute(
            update(Listing).where(Listing.scenario_id == scenario_id).values(heart_count=Listing.heart_count + 1)
        )


async def remove_heart(session: AsyncSession, user_id: uuid.UUID, scenario_id: uuid.UUID) -> None:
    """관심을 거둔다. 없으면 아무것도 하지 않는다."""
    removed = await session.scalar(
        delete(ListingHeart)
        .where(ListingHeart.user_id == user_id, ListingHeart.scenario_id == scenario_id)
        .returning(ListingHeart.scenario_id)
    )
    if removed is not None:
        await session.execute(
            update(Listing).where(Listing.scenario_id == scenario_id).values(heart_count=Listing.heart_count - 1)
        )


async def heart_state(session: AsyncSession, user_id: uuid.UUID, scenario_id: uuid.UUID) -> tuple[bool, int]:
    """내가 관심을 두었는지와 관심의 수. 공개 정보가 없으면 (False, 0) 이다."""
    hearted = select(ListingHeart.user_id).where(
        ListingHeart.user_id == user_id, ListingHeart.scenario_id == scenario_id
    )
    row = (
        await session.execute(select(hearted.exists(), Listing.heart_count).where(Listing.scenario_id == scenario_id))
    ).first()
    return (bool(row[0]), row[1]) if row else (False, 0)


def hearted_by(user_id: uuid.UUID, allowed_ratings: list[Rating]) -> Select[PublicRow]:
    """내가 관심을 둔 것 가운데 지금 볼 수 있는 것. 링크 공개도 든다(내가 이미 연 것이다)."""
    return visible(allowed_ratings).join(
        ListingHeart, (ListingHeart.scenario_id == Listing.scenario_id) & (ListingHeart.user_id == user_id)
    )


async def list_hearted(
    session: AsyncSession, user_id: uuid.UUID, allowed_ratings: list[Rating], limit: int, offset: int
) -> list[PublicRow]:
    """내 관심 작품의 한 쪽. 최근에 둔 것부터다."""
    query = (
        hearted_by(user_id, allowed_ratings)
        .options(defer(ScenarioVersion.snapshot))
        .order_by(ListingHeart.created_at.desc(), Listing.scenario_id)
        .limit(limit)
        .offset(offset)
    )
    return [tuple(row) for row in await session.execute(query)]


async def count_hearted(session: AsyncSession, user_id: uuid.UUID, allowed_ratings: list[Rating]) -> int:
    """내 관심 작품의 수(지금 볼 수 있는 것만)."""
    query = hearted_by(user_id, allowed_ratings).with_only_columns(func.count()).order_by(None)
    return await session.scalar(query) or 0


async def remove_all_of(session: AsyncSession, user_id: uuid.UUID) -> None:
    """그 사람의 관심을 모두 거둔다(탈퇴). 수를 먼저 빼고 줄을 지운다."""
    mine = select(ListingHeart.scenario_id).where(ListingHeart.user_id == user_id)
    await session.execute(
        update(Listing).where(Listing.scenario_id.in_(mine)).values(heart_count=Listing.heart_count - 1)
    )
    await session.execute(delete(ListingHeart).where(ListingHeart.user_id == user_id))
