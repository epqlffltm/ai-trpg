# trpg-server/app/assets/bestiaries/repository.py

"""
도감의 몬스터를 DB 에서 읽고 쓴다. 커밋하지 않는다.

도감 자신은 공통 저장소(app/assets/repository.py)가 다룬다.
여기의 함수는 "누구의 것인가"를 묻지 않는다. 도감이 그 사람의 것인지는 서비스가 먼저 확인한다.
대신 모든 함수가 도감의 ID 를 받는다. 몬스터의 ID 만으로 남의 도감의 몬스터를 건드리는 길이 없다.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.bestiaries.models import Monster


def add_monster(session: AsyncSession, monster: Monster) -> None:
    """새 몬스터를 세션에 올린다."""
    session.add(monster)


async def find_monster(session: AsyncSession, bestiary_id: uuid.UUID, monster_id: uuid.UUID) -> Monster | None:
    """도감의 몬스터 하나를 찾는다. 없거나 다른 도감의 몬스터면 None."""
    query = select(Monster).where(Monster.id == monster_id, Monster.bestiary_id == bestiary_id)
    return await session.scalar(query)


async def list_monsters(session: AsyncSession, bestiary_id: uuid.UUID) -> list[Monster]:
    """도감의 몬스터를 만든 순서대로 전부 돌려준다. 개수에 상한이 있어서 쪽을 나누지 않는다."""
    query = select(Monster).where(Monster.bestiary_id == bestiary_id).order_by(Monster.created_at, Monster.id)
    result = await session.scalars(query)
    return list(result)


async def count_monsters(session: AsyncSession, bestiary_id: uuid.UUID) -> int:
    """도감의 몬스터가 몇인지 센다."""
    query = select(func.count()).select_from(Monster).where(Monster.bestiary_id == bestiary_id)
    return await session.scalar(query) or 0


async def delete_monster(session: AsyncSession, monster: Monster) -> None:
    """몬스터의 행을 지운다."""
    await session.delete(monster)
