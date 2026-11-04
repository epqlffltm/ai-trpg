# asset-server/app/hearts/repository.py

"""
관심(하트, #989)을 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

작품의 관심 수(heart_count)는 관심의 줄을 넣고 지운 것과 같은 트랜잭션에서 하나씩 더하고 뺀다.
줄이 실제로 생기거나 지워졌을 때만 바꾼다. 두 번 눌러도, 동시에 눌러도 수가 어긋나지 않는다(기본 키가 한 번만 받는다).
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.hearts.kinds import HeartKind
from app.ratings import Rating


def mine(kind: HeartKind, user_id: uuid.UUID, work_id: uuid.UUID):
    """그 사람이 그 작품에 둔 관심의 조건."""
    return (kind.heart.user_id == user_id) & (kind.heart_work_id == work_id)


async def change_count(session: AsyncSession, kind: HeartKind, work_id: uuid.UUID, step: int) -> None:
    """작품의 관심 수를 step 만큼 바꾼다."""
    await session.execute(
        update(kind.work).where(kind.work.id == work_id).values(heart_count=kind.work.heart_count + step)
    )


async def add_heart(session: AsyncSession, kind: HeartKind, user_id: uuid.UUID, work_id: uuid.UUID) -> None:
    """관심을 둔다. 이미 있으면 아무것도 하지 않는다."""
    values = {'user_id': user_id, kind.heart_work_id.key: work_id}
    inserted = await session.scalar(
        insert(kind.heart).values(values).on_conflict_do_nothing().returning(kind.heart_work_id)
    )
    if inserted is not None:
        await change_count(session, kind, work_id, 1)


async def remove_heart(session: AsyncSession, kind: HeartKind, user_id: uuid.UUID, work_id: uuid.UUID) -> None:
    """관심을 거둔다. 없으면 아무것도 하지 않는다."""
    removed = await session.scalar(delete(kind.heart).where(mine(kind, user_id, work_id)).returning(kind.heart_work_id))
    if removed is not None:
        await change_count(session, kind, work_id, -1)


async def heart_state(
    session: AsyncSession, kind: HeartKind, user_id: uuid.UUID, work_id: uuid.UUID
) -> tuple[bool, int]:
    """내가 관심을 두었는지와 관심의 수. 작품이 없으면 (False, 0) 이다."""
    hearted = select(kind.heart.user_id).where(mine(kind, user_id, work_id)).exists()
    row = (await session.execute(select(hearted, kind.work.heart_count).where(kind.work.id == work_id))).first()
    return (bool(row[0]), row[1]) if row else (False, 0)


def hearted_by(kind: HeartKind, user_id: uuid.UUID, ratings: Sequence[Rating]) -> Select:
    """내가 관심을 둔 것 가운데 지금 열 수 있는 것과 그 마지막 판. 링크 공개도 든다(내가 이미 연 것이다)."""
    return (
        select(kind.work, kind.version)
        .join(kind.version, kind.latest_join())
        .join(kind.heart, (kind.heart_work_id == kind.work.id) & (kind.heart.user_id == user_id))
        .where(kind.opened(ratings))
    )


async def list_hearted(
    session: AsyncSession, kind: HeartKind, user_id: uuid.UUID, ratings: Sequence[Rating], limit: int, offset: int
) -> list[tuple[Any, Any]]:
    """내 관심 작품의 한 쪽. 최근에 둔 것부터다."""
    query = (
        hearted_by(kind, user_id, ratings)
        .order_by(kind.heart.created_at.desc(), kind.work.id)
        .limit(limit)
        .offset(offset)
    )
    return [(work, version) for work, version in (await session.execute(query)).all()]


async def count_hearted(session: AsyncSession, kind: HeartKind, user_id: uuid.UUID, ratings: Sequence[Rating]) -> int:
    """내 관심 작품의 수(지금 열 수 있는 것만)."""
    query = hearted_by(kind, user_id, ratings).with_only_columns(func.count()).order_by(None)
    return await session.scalar(query) or 0


async def remove_all_of(session: AsyncSession, kind: HeartKind, user_id: uuid.UUID) -> None:
    """그 사람의 관심을 모두 거둔다(탈퇴). 수를 먼저 빼고 줄을 지운다."""
    works = select(kind.heart_work_id).where(kind.heart.user_id == user_id)
    await session.execute(
        update(kind.work).where(kind.work.id.in_(works)).values(heart_count=kind.work.heart_count - 1)
    )
    await session.execute(delete(kind.heart).where(kind.heart.user_id == user_id))
