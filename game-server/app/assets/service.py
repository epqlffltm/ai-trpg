# game-server/app/assets/service.py

"""
세계관을 만들고, 읽고, 고치고, 지우는 규칙.

HTTP 를 모른다. 요청이나 상태 코드를 다루지 않고, 안 되는 일은 예외로 알린다.
SQL 을 모른다. DB 에서 읽고 쓰는 일은 repository.py 에 맡긴다.
어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import repository
from app.assets.models import Asset, AssetType, World
from app.assets.schemas import WorldCreate, WorldUpdate

# 자산의 공통 부분에 속하는 칸. 나머지 칸은 세계관의 내용에 속한다
ASSET_FIELDS = {'title', 'description', 'rating'}


class WorldNotFoundError(Exception):
    """
    그런 세계관이 없다.

    남의 것인 경우도 이 예외다. "있지만 네 것이 아니다"라고 알려 주면 그 ID 의 자산이 있다는 것이 드러난다.
    """


def build_world(owner_id: uuid.UUID, data: WorldCreate) -> World:
    """입력에서 세계관 객체를 만든다. 아직 저장하지 않는다."""
    asset = Asset(
        owner_id=owner_id,
        type=AssetType.WORLD,
        title=data.title,
        description=data.description,
        rating=data.rating,
    )
    return World(asset=asset, setting=data.setting, gm_notes=data.gm_notes)


def apply_changes(world: World, data: WorldUpdate) -> None:
    """보낸 칸만 세계관에 반영한다."""
    # exclude_unset: 요청에 실제로 들어 있던 칸만 꺼낸다. 보내지 않은 칸을 None 으로 덮어쓰지 않는다
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        target = world.asset if field in ASSET_FIELDS else world
        setattr(target, field, value)

    # 내용(worlds)만 바뀌어도 고친 시각은 공통 부분(assets)에 있다. 직접 갱신한다
    world.asset.updated_at = func.now()


async def create_world(session: AsyncSession, owner_id: uuid.UUID, data: WorldCreate) -> World:
    """세계관을 만든다. 공통 부분과 내용이 한 묶음으로 저장된다."""
    world = build_world(owner_id, data)
    repository.add_world(session, world)
    await session.commit()
    return world


async def get_world(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID) -> World:
    """자기 세계관 하나를 돌려준다. 없으면 WorldNotFoundError."""
    world = await repository.find_world(session, owner_id, world_id)
    if world is None:
        raise WorldNotFoundError
    return world


async def list_worlds(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[World], int]:
    """자기 세계관의 한 쪽과 전체 개수를 돌려준다."""
    worlds = await repository.list_worlds(session, owner_id, limit, offset)
    total = await repository.count_worlds(session, owner_id)
    return worlds, total


async def update_world(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID, data: WorldUpdate) -> World:
    """자기 세계관을 고친다. 없으면 WorldNotFoundError."""
    world = await get_world(session, owner_id, world_id)
    apply_changes(world, data)
    await session.commit()
    # 고친 시각은 DB 가 정했다. 그 값을 다시 읽어 온다
    await session.refresh(world.asset)
    return world


async def delete_world(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID) -> None:
    """
    자기 세계관을 지운다. 없으면 WorldNotFoundError.

    행을 지우지 않고 지운 시각을 적는다. 그 뒤로는 어떤 조회에도 나오지 않는다.
    """
    world = await get_world(session, owner_id, world_id)
    world.asset.deleted_at = func.now()
    await session.commit()
