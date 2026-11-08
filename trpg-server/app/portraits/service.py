# trpg-server/app/portraits/service.py

"""
제작자의 캐릭터 그림(#983)을 올리고 보여 준다.

  - 올리기: 한 사람이 올릴 수 있는 수(PORTRAIT_MAX_PER_OWNER)를 보고, asset 에 올린 사람의 토큰으로 맡긴 뒤 기록한다.
    asset 에 맡긴 뒤 기록하지 못하면 asset 에 주인 없는 그림이 하나 남는다(기록이 없으니 아무도 붙이지 못한다)
  - 보기: 올린 사람은 자기 그림을 본다. 테이블에 앉은 사람은 그 테이블의 판(프리젠)에 붙은 그림을 본다.
    공개된 시나리오를 볼 수 있는 사람은 공개 중인 판의 프리젠에 붙은 그림과 그 시나리오의 표지(#1164)를 본다
    (로그인하지 않아도 전체 이용가는 본다)
  - 지우기: 어느 초안이나 판에도 붙지 않고 표지도 아닌 그림만 지운다(2026-11-05 결정).
    쓰이고 있으면 쓰는 시나리오들을 알린다.
    진행 중인 테이블의 그림이 사라지지 않게 하려는 것이다. 기록을 지워 저장한 뒤 asset 의 그림을 지운다.
    asset 에서 지우지 못하면 asset 에 그림이 남는다(기록이 없으니 아무도 붙이거나 받지 못한다)
  - asset 을 부르는 동안 DB 의 트랜잭션을 열어 두지 않는다. 세션을 나눠 쓴다
"""

import logging
import uuid

from server_core.auth.tokens import AccessClaims
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.asset_server.client import AssetClient, AssetNotFoundError, AssetUnavailableError, ImageContent
from app.assets.scenarios.snapshot import read_snapshot
from app.listings.service import get_public
from app.portraits import repository
from app.portraits.models import Portrait
from app.portraits.schemas import PortraitOut, PortraitPage
from app.portraits.seats import table_portraits
from app.tables.service import get_table

logger = logging.getLogger(__name__)

# 한 사람이 올릴 수 있는 그림의 수. 끝없이 올려 저장소를 채우는 일을 막는다
PORTRAIT_MAX_PER_OWNER = 100


class PortraitLimitError(Exception):
    """올릴 수 있는 수를 다 채웠다."""


class PortraitNotFoundError(Exception):
    """그런 그림이 없다(남의 것, asset 에서 사라진 것 포함)."""


class PortraitInUseError(Exception):
    """초안이나 판의 프리젠에 붙었거나 표지인 그림이라 지우지 못한다. scenarios 는 쓰는 시나리오들의 (id, 제목)이다."""

    def __init__(self, scenarios: list[tuple[uuid.UUID, str]]) -> None:
        super().__init__(len(scenarios))
        self.scenarios = scenarios


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


async def fetch_image(asset: AssetClient, image_id: uuid.UUID) -> ImageContent:
    """이 서버가 맡긴 그림의 바이트. asset 에서 사라졌으면 PortraitNotFoundError."""
    try:
        return await asset.fetch_kept(image_id)
    except AssetNotFoundError as error:
        logger.warning('기록은 있는데 asset 에 그림이 없습니다', extra={'image_id': str(image_id)})
        raise PortraitNotFoundError from error


async def portrait_image(
    session_factory: async_sessionmaker[AsyncSession], asset: AssetClient, owner_id: uuid.UUID, image_id: uuid.UUID
) -> ImageContent:
    """내가 올린 그림의 바이트. 남의 것이나 asset 에서 사라진 것은 PortraitNotFoundError."""
    portrait = await find_mine(session_factory, owner_id, image_id)
    return await fetch_image(asset, portrait.id)


async def require_table_portrait(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, table_id: uuid.UUID, image_id: uuid.UUID
) -> None:
    """
    앉은 테이블의 판에 붙은 그림인지 본다.

    앉지 않은 테이블이면 TableNotFoundError(404), 그 판의 그림이 아니면 PortraitNotFoundError.
    """
    async with session_factory() as session:
        table = await get_table(session, user_id, table_id)
        if image_id not in table_portraits(table.content):
            raise PortraitNotFoundError


async def table_portrait_image(
    session_factory: async_sessionmaker[AsyncSession],
    asset: AssetClient,
    user_id: uuid.UUID,
    table_id: uuid.UUID,
    image_id: uuid.UUID,
) -> ImageContent:
    """앉은 테이블의 캐릭터 그림의 바이트."""
    await require_table_portrait(session_factory, user_id, table_id, image_id)
    return await fetch_image(asset, image_id)


async def require_listing_portrait(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: AccessClaims | None,
    scenario_id: uuid.UUID,
    image_id: uuid.UUID,
) -> None:
    """
    볼 수 있는 공개 시나리오의 공개 중인 판에 붙은 그림(프리젠, 업적)이거나 그 시나리오의 표지(#1164)인지 본다.

    볼 수 없는 시나리오(공개하지 않음, 볼 수 없는 등급)면 AssetNotFoundError(404), 그 판의 그림도 표지도 아니면
    PortraitNotFoundError.
    """
    async with session_factory() as session:
        listing, _, version = await get_public(session, viewer, scenario_id)
    if image_id == listing.cover_image_id:
        return
    snapshot = read_snapshot(version.snapshot)
    shown = [*(pregen.image_id for pregen in snapshot.pregens), *(one.image_id for one in snapshot.achievements)]
    if image_id not in {image for image in shown if image is not None}:
        raise PortraitNotFoundError


async def listing_portrait_image(
    session_factory: async_sessionmaker[AsyncSession],
    asset: AssetClient,
    viewer: AccessClaims | None,
    scenario_id: uuid.UUID,
    image_id: uuid.UUID,
) -> ImageContent:
    """공개된 시나리오의 프리젠 그림, 업적의 그림, 표지의 바이트."""
    await require_listing_portrait(session_factory, viewer, scenario_id, image_id)
    return await fetch_image(asset, image_id)


async def forget_portrait(
    session_factory: async_sessionmaker[AsyncSession], owner_id: uuid.UUID, image_id: uuid.UUID
) -> None:
    """
    쓰이지 않는 내 그림의 기록을 지우고 저장한다.

    남의 것이나 없는 것이면 PortraitNotFoundError, 초안이나 판에 붙어 있거나 표지면 PortraitInUseError.
    행을 혼자 잠그고 보므로, 지우는 동안 다른 저장이 이 그림을 새로 붙이지 못한다.
    """
    async with session_factory() as session:
        if await repository.lock_owned(session, owner_id, image_id) is None:
            raise PortraitNotFoundError
        scenarios = await repository.using_scenarios(session, image_id)
        if scenarios:
            raise PortraitInUseError(scenarios)
        await repository.delete_portrait(session, image_id)
        await session.commit()


async def discard_image(asset: AssetClient, token: str, image_id: uuid.UUID) -> None:
    """asset 의 그림을 지운다. 지우지 못하면 로그만 남긴다(기록은 이미 지웠다)."""
    try:
        await asset.discard_image(token, image_id)
    except AssetUnavailableError:
        logger.warning(
            '기록은 지웠지만 asset 의 그림을 지우지 못했습니다',
            extra={'image_id': str(image_id), 'error_code': 'portrait.discard_failed'},
        )


async def delete_portrait(
    session_factory: async_sessionmaker[AsyncSession],
    asset: AssetClient,
    owner_id: uuid.UUID,
    token: str,
    image_id: uuid.UUID,
) -> None:
    """쓰이지 않는 내 그림을 지운다. 기록을 먼저, asset 의 그림을 나중에 지운다."""
    await forget_portrait(session_factory, owner_id, image_id)
    await discard_image(asset, token, image_id)
