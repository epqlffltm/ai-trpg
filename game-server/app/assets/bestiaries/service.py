# game-server/app/assets/bestiaries/service.py

"""
도감과 그 몬스터를 만들고, 읽고, 고치고, 지운다.

도감 자신의 규칙은 모든 자산에 공통이라 app/assets/service.py 에 있다.
여기에는 몬스터의 규칙이 있다. 몬스터는 도감에 딸려 있어서, 도감의 주인만 다룰 수 있다.
몬스터가 바뀌면 도감이 바뀐 것이다. 도감의 고친 시각을 함께 갱신한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.bestiaries import repository
from app.assets.bestiaries.models import BESTIARY_MAX_MONSTERS, Bestiary, Monster
from app.assets.bestiaries.schemas import BestiaryCreate, BestiaryUpdate, MonsterCreate, MonsterUpdate
from app.assets.models import AssetType
from app.assets.service import AssetNotFoundError


class BestiaryFullError(Exception):
    """도감의 몬스터가 상한에 닿아 더 넣을 수 없다."""


# --- 도감 ---


def build_bestiary(owner_id: uuid.UUID, data: BestiaryCreate) -> Bestiary:
    """입력에서 도감 객체를 만든다. 아직 저장하지 않는다."""
    return Bestiary(asset=assets.build_asset(owner_id, AssetType.BESTIARY, data))


async def create_bestiary(session: AsyncSession, owner_id: uuid.UUID, data: BestiaryCreate) -> Bestiary:
    """도감을 만든다. 몬스터는 없다."""
    return await assets.create(session, build_bestiary(owner_id, data))


async def get_bestiary(session: AsyncSession, owner_id: uuid.UUID, bestiary_id: uuid.UUID) -> Bestiary:
    """자기 도감 하나를 돌려준다. 없으면 AssetNotFoundError."""
    return await assets.get_owned(session, Bestiary, owner_id, bestiary_id)


async def list_bestiaries(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Bestiary], int]:
    """자기 도감의 한 쪽과 전체 개수를 돌려준다."""
    return await assets.list_owned(session, Bestiary, owner_id, limit, offset)


async def update_bestiary(
    session: AsyncSession, owner_id: uuid.UUID, bestiary_id: uuid.UUID, data: BestiaryUpdate
) -> Bestiary:
    """자기 도감을 고친다. 없으면 AssetNotFoundError."""
    return await assets.update_owned(session, Bestiary, owner_id, bestiary_id, data)


async def delete_bestiary(session: AsyncSession, owner_id: uuid.UUID, bestiary_id: uuid.UUID) -> None:
    """자기 도감을 지운다. 없으면 AssetNotFoundError. 몬스터는 도감과 함께 보이지 않게 된다."""
    await assets.delete_owned(session, Bestiary, owner_id, bestiary_id)


# --- 몬스터 ---


def build_monster(bestiary_id: uuid.UUID, data: MonsterCreate) -> Monster:
    """입력에서 몬스터 객체를 만든다. 아직 저장하지 않는다."""
    return Monster(bestiary_id=bestiary_id, name=data.name, content=data.content, kind=data.kind)


def apply_monster_changes(monster: Monster, data: MonsterUpdate) -> None:
    """보낸 칸만 몬스터에 반영한다. null 은 "보내지 않았다"로 본다."""
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(monster, field, value)


async def get_monster(session: AsyncSession, bestiary_id: uuid.UUID, monster_id: uuid.UUID) -> Monster:
    """도감의 몬스터 하나를 돌려준다. 없으면 AssetNotFoundError."""
    monster = await repository.find_monster(session, bestiary_id, monster_id)
    if monster is None:
        raise AssetNotFoundError
    return monster


async def add_monster(
    session: AsyncSession, owner_id: uuid.UUID, bestiary_id: uuid.UUID, data: MonsterCreate
) -> Monster:
    """
    자기 도감에 몬스터를 더한다. 도감이 없으면 AssetNotFoundError, 가득 찼으면 BestiaryFullError.

    개수를 세고 나서 더한다. 두 요청이 동시에 세면 둘 다 "아직 자리가 있다"고 보고 상한을 넘긴다.
    그래서 세기 전에 도감을 잠근다. 같은 도감에 더하려는 다른 요청은 이 저장이 끝날 때까지 기다린다.
    """
    bestiary = await assets.lock_owned(session, Bestiary, owner_id, bestiary_id)
    if await repository.count_monsters(session, bestiary_id) >= BESTIARY_MAX_MONSTERS:
        raise BestiaryFullError

    monster = build_monster(bestiary_id, data)
    repository.add_monster(session, monster)
    assets.touch(bestiary)
    await session.commit()
    return monster


async def list_monsters(session: AsyncSession, owner_id: uuid.UUID, bestiary_id: uuid.UUID) -> list[Monster]:
    """자기 도감의 몬스터를 만든 순서대로 전부 돌려준다. 도감이 없으면 AssetNotFoundError."""
    await get_bestiary(session, owner_id, bestiary_id)
    return await repository.list_monsters(session, bestiary_id)


async def update_monster(
    session: AsyncSession, owner_id: uuid.UUID, bestiary_id: uuid.UUID, monster_id: uuid.UUID, data: MonsterUpdate
) -> Monster:
    """자기 도감의 몬스터를 고친다. 도감이나 몬스터가 없으면 AssetNotFoundError."""
    bestiary = await get_bestiary(session, owner_id, bestiary_id)
    monster = await get_monster(session, bestiary_id, monster_id)
    apply_monster_changes(monster, data)
    assets.touch(bestiary)
    await session.commit()
    # 고친 시각은 DB 가 정했다. 그 값을 다시 읽어 온다
    await session.refresh(monster)
    return monster


async def delete_monster(
    session: AsyncSession, owner_id: uuid.UUID, bestiary_id: uuid.UUID, monster_id: uuid.UUID
) -> None:
    """자기 도감의 몬스터를 지운다. 도감이나 몬스터가 없으면 AssetNotFoundError."""
    bestiary = await get_bestiary(session, owner_id, bestiary_id)
    monster = await get_monster(session, bestiary_id, monster_id)
    await repository.delete_monster(session, monster)
    assets.touch(bestiary)
    await session.commit()
