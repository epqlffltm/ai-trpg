# game-server/app/assets/worlds/service.py

"""
세계관을 만들고, 읽고, 고치고, 지운다.

규칙의 대부분은 모든 자산에 공통이라 app/assets/service.py 에 있다.
여기에는 세계관만의 것(입력에서 세계관을 만드는 방법)과, 공통 규칙에 "세계관"을 넘겨 부르는 함수가 있다.
세계관에만 해당하는 규칙이 생기면 여기에 넣는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.models import AssetType, World
from app.assets.worlds.schemas import WorldCreate, WorldUpdate


def build_world(owner_id: uuid.UUID, data: WorldCreate) -> World:
    """입력에서 세계관 객체를 만든다. 아직 저장하지 않는다."""
    asset = assets.build_asset(owner_id, AssetType.WORLD, data)
    return World(asset=asset, setting=data.setting, gm_notes=data.gm_notes)


async def create_world(session: AsyncSession, owner_id: uuid.UUID, data: WorldCreate) -> World:
    """세계관을 만든다."""
    return await assets.create(session, build_world(owner_id, data))


async def get_world(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID) -> World:
    """자기 세계관 하나를 돌려준다. 없으면 AssetNotFoundError."""
    return await assets.get_owned(session, World, owner_id, world_id)


async def list_worlds(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[World], int]:
    """자기 세계관의 한 쪽과 전체 개수를 돌려준다."""
    return await assets.list_owned(session, World, owner_id, limit, offset)


async def update_world(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID, data: WorldUpdate) -> World:
    """자기 세계관을 고친다. 없으면 AssetNotFoundError."""
    return await assets.update_owned(session, World, owner_id, world_id, data)


async def delete_world(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID) -> None:
    """자기 세계관을 지운다. 없으면 AssetNotFoundError."""
    await assets.delete_owned(session, World, owner_id, world_id)
