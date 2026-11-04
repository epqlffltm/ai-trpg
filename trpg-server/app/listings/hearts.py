# trpg-server/app/listings/hearts.py

"""
시나리오의 관심(하트, #989)의 규칙.

  - 둘 수 있는 것은 공개 중이고 내가 볼 수 있는 시나리오다(소개를 열 수 있는 것, 링크 공개도 된다).
    아니면 없는 것(404)이다
  - 거두는 것은 언제나 된다. 공개를 내렸거나 볼 수 없게 된 것도 거둔다
  - 두 번 두거나 두 번 거둬도 결과가 같다(멱등)
"""

import uuid

from server_core.auth.tokens import AccessClaims
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.ratings import allowed_ratings
from app.listings import heart_repository as hearts
from app.listings import service
from app.listings.repository import PublicRow
from app.listings.schemas import HeartState


async def state_of(session: AsyncSession, viewer: AccessClaims, scenario_id: uuid.UUID) -> HeartState:
    """내가 관심을 두었는지와 관심의 수. 볼 수 없으면 AssetNotFoundError."""
    await service.get_public(session, viewer, scenario_id)
    hearted, count = await hearts.heart_state(session, viewer.user_id, scenario_id)
    return HeartState(hearted=hearted, heart_count=count)


async def put_heart(session: AsyncSession, viewer: AccessClaims, scenario_id: uuid.UUID) -> HeartState:
    """관심을 둔다. 볼 수 없으면 AssetNotFoundError."""
    await service.get_public(session, viewer, scenario_id)
    await hearts.add_heart(session, viewer.user_id, scenario_id)
    await session.commit()
    hearted, count = await hearts.heart_state(session, viewer.user_id, scenario_id)
    return HeartState(hearted=hearted, heart_count=count)


async def take_heart(session: AsyncSession, viewer: AccessClaims, scenario_id: uuid.UUID) -> HeartState:
    """관심을 거둔다. 언제나 된다."""
    await hearts.remove_heart(session, viewer.user_id, scenario_id)
    await session.commit()
    hearted, count = await hearts.heart_state(session, viewer.user_id, scenario_id)
    return HeartState(hearted=hearted, heart_count=count)


async def list_mine(
    session: AsyncSession, viewer: AccessClaims, limit: int, offset: int
) -> tuple[list[PublicRow], int]:
    """내 관심 작품의 한 쪽과 전체 수. 지금 볼 수 있는 것만이다."""
    ratings = allowed_ratings(viewer)
    rows = await hearts.list_hearted(session, viewer.user_id, ratings, limit, offset)
    return rows, await hearts.count_hearted(session, viewer.user_id, ratings)
