# notification-server/app/follows/repository.py

"""
제작자 팔로우(creator_follows)에 닿는 SQL(#989). 규칙을 모른다. 상한과 자기 자신은 service.py 가 본다. 커밋하지 않는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.follows.models import CreatorFollow


async def lock_follower(session: AsyncSession, follower_id: uuid.UUID) -> None:
    """
    한 사람의 팔로우를 트랜잭션이 끝날 때까지 하나씩 하게 잠근다.

    상한을 세고 넣는 사이에 같은 사람의 다른 요청이 끼어 상한을 넘지 않게 한다. 다른 사람은 기다리지 않는다.
    """
    key = func.hashtextextended(str(follower_id), 989)
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def is_following(session: AsyncSession, follower_id: uuid.UUID, creator_id: uuid.UUID) -> bool:
    """이 사람이 그 제작자를 팔로우하는가. 기본 키로 한 줄을 찾는다."""
    statement = select(exists().where(CreatorFollow.follower_id == follower_id, CreatorFollow.creator_id == creator_id))
    return bool(await session.scalar(statement))


async def count_following(session: AsyncSession, follower_id: uuid.UUID) -> int:
    """이 사람이 팔로우하는 제작자의 수."""
    statement = select(func.count()).select_from(CreatorFollow).where(CreatorFollow.follower_id == follower_id)
    return await session.scalar(statement) or 0


async def count_followers(session: AsyncSession, creator_id: uuid.UUID) -> int:
    """그 제작자의 팔로워 수. 색인(creator_id)으로 센다."""
    statement = select(func.count()).select_from(CreatorFollow).where(CreatorFollow.creator_id == creator_id)
    return await session.scalar(statement) or 0


async def insert_follow(session: AsyncSession, follower_id: uuid.UUID, creator_id: uuid.UUID, now: datetime) -> None:
    """팔로우한다. 이미 하고 있으면 아무것도 하지 않는다(처음 한 시각 그대로)."""
    statement = (
        insert(CreatorFollow)
        .values(follower_id=follower_id, creator_id=creator_id, created_at=now)
        .on_conflict_do_nothing(index_elements=[CreatorFollow.follower_id, CreatorFollow.creator_id])
    )
    await session.execute(statement)


async def delete_follow(session: AsyncSession, follower_id: uuid.UUID, creator_id: uuid.UUID) -> None:
    """팔로우를 끊는다. 하고 있지 않으면 아무것도 하지 않는다."""
    await session.execute(
        delete(CreatorFollow).where(CreatorFollow.follower_id == follower_id, CreatorFollow.creator_id == creator_id)
    )


async def list_following(
    session: AsyncSession, follower_id: uuid.UUID, limit: int, offset: int
) -> list[tuple[uuid.UUID, datetime]]:
    """내 팔로잉의 한 쪽. 최근에 팔로우한 것부터다."""
    statement = (
        select(CreatorFollow.creator_id, CreatorFollow.created_at)
        .where(CreatorFollow.follower_id == follower_id)
        .order_by(CreatorFollow.created_at.desc(), CreatorFollow.creator_id)
        .limit(limit)
        .offset(offset)
    )
    return [(creator_id, created_at) for creator_id, created_at in (await session.execute(statement)).all()]
