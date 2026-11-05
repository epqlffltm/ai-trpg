# trpg-server/app/portraits/service.py

"""
제작자의 캐릭터 그림(#983)을 올리고 보여 준다.

  - 올리기: 한 사람이 올릴 수 있는 수(PORTRAIT_MAX_PER_OWNER)를 보고, asset 에 올린 사람의 토큰으로 맡긴 뒤 기록한다.
    asset 에 맡긴 뒤 기록하지 못하면 asset 에 주인 없는 그림이 하나 남는다(기록이 없으니 아무도 붙이지 못한다)
  - 보기: 지금은 올린 사람만 본다. 테이블의 사람과 공개 시나리오를 보는 사람은 프리젠에 붙인 뒤(다음 단계)에 연다
  - asset 을 부르는 동안 DB 의 트랜잭션을 열어 두지 않는다. 세션을 나눠 쓴다
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.asset_server.client import AssetClient, AssetNotFoundError, ImageContent
from app.portraits import repository
from app.portraits.models import Portrait
from app.portraits.schemas import PortraitOut, PortraitPage

logger = logging.getLogger(__name__)

# 한 사람이 올릴 수 있는 그림의 수. 끝없이 올려 저장소를 채우는 일을 막는다
PORTRAIT_MAX_PER_OWNER = 100


class PortraitLimitError(Exception):
    """올릴 수 있는 수를 다 채웠다."""


class PortraitNotFoundError(Exception):
    """그런 그림이 없다(남의 것, asset 에서 사라진 것 포함)."""


def to_out(portrait: Portrait) -> PortraitOut:
    """기록을 응답의 모양으로 바꾼다."""
    return PortraitOut(id=portrait.id, created_at=portrait.created_at)


async def ensure_room(session_factory: async_sessionmaker[AsyncSession], owner_id: uuid.UUID) -> None:
    """더 올릴 수 있는지 본다. 다 채웠으면 PortraitLimitError."""
    async with session_factory() as session:
        if await repository.count_owned(session, owner_id) >= PORTRAIT_MAX_PER_OWNER:
            raise PortraitLimitError


async def record(
    session_factory: async_sessionmaker[AsyncSession], image_id: uuid.UUID, owner_id: uuid.UUID
) -> PortraitOut:
    """맡긴 그림을 기록하고 저장한다."""
    async with session_factory() as session:
        portrait = repository.add(session, image_id, owner_id)
        await session.commit()
        await session.refresh(portrait)
        return to_out(portrait)


async def upload_portrait(
    session_factory: async_sessionmaker[AsyncSession],
    asset: AssetClient,
    token: str,
    owner_id: uuid.UUID,
    data: bytes,
) -> PortraitOut:
    """그림을 올린다. asset 이 그림을 받지 않으면 ImageRejectedError, 닿지 못하면 AssetUnavailableError."""
    await ensure_room(session_factory, owner_id)
    image_id = await asset.keep_image(token, data)
    return await record(session_factory, image_id, owner_id)


async def list_portraits(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> PortraitPage:
    """내가 올린 그림들. 최근 것부터다."""
    portraits, total = await repository.list_owned(session, owner_id, limit, offset)
    return PortraitPage(items=[to_out(portrait) for portrait in portraits], total=total)


async def find_mine(
    session_factory: async_sessionmaker[AsyncSession], owner_id: uuid.UUID, image_id: uuid.UUID
) -> Portrait:
    """내가 올린 그림 하나. 없으면 PortraitNotFoundError."""
    async with session_factory() as session:
        portrait = await repository.find_owned(session, owner_id, image_id)
    if portrait is None:
        raise PortraitNotFoundError
    return portrait


async def portrait_image(
    session_factory: async_sessionmaker[AsyncSession], asset: AssetClient, owner_id: uuid.UUID, image_id: uuid.UUID
) -> ImageContent:
    """내가 올린 그림의 바이트. 남의 것이나 asset 에서 사라진 것은 PortraitNotFoundError."""
    portrait = await find_mine(session_factory, owner_id, image_id)
    try:
        return await asset.fetch_kept(portrait.id)
    except AssetNotFoundError as error:
        logger.warning('기록은 있는데 asset 에 그림이 없습니다', extra={'image_id': str(portrait.id)})
        raise PortraitNotFoundError from error
