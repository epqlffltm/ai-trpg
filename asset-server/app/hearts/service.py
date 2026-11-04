# asset-server/app/hearts/service.py

"""
관심(하트, #989)의 규칙. 캐릭터와 세계관이 같다(trpg-server 의 시나리오와도 같다).

  - 둘 수 있는 것은 내가 주소로 열 수 있는 작품이다(공개나 링크 공개, 숨기지 않음, 볼 수 있는 등급).
    아니면 not_found 를 던진다
  - 거두는 것은 언제나 된다. 비공개로 돌렸거나 숨긴 것도 거둔다
  - 두 번 두거나 두 번 거둬도 결과가 같다(멱등)
"""

import uuid
from collections.abc import Callable
from typing import Any

from server_core.auth.tokens import AccessClaims
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hearts import repository
from app.hearts.kinds import HeartKind
from app.hearts.schemas import HeartState
from app.ratings import allowed_ratings


async def require_opened(
    session: AsyncSession, kind: HeartKind, viewer: AccessClaims, work_id: uuid.UUID, not_found: Callable[[], Exception]
) -> None:
    """내가 주소로 열 수 있는 작품이 아니면 not_found() 를 던진다."""
    query = (
        select(kind.work.id)
        .join(kind.version, kind.latest_join())
        .where(kind.work.id == work_id, kind.opened(allowed_ratings(viewer)))
    )
    if await session.scalar(query) is None:
        raise not_found()


async def current_state(session: AsyncSession, kind: HeartKind, viewer: AccessClaims, work_id: uuid.UUID) -> HeartState:
    """지금 값을 읽어 응답으로 만든다."""
    hearted, count = await repository.heart_state(session, kind, viewer.user_id, work_id)
    return HeartState(hearted=hearted, heart_count=count)


async def state_of(
    session: AsyncSession, kind: HeartKind, viewer: AccessClaims, work_id: uuid.UUID, not_found: Callable[[], Exception]
) -> HeartState:
    """내가 관심을 두었는지와 관심의 수. 열 수 없으면 not_found."""
    await require_opened(session, kind, viewer, work_id, not_found)
    return await current_state(session, kind, viewer, work_id)


async def put_heart(
    session: AsyncSession, kind: HeartKind, viewer: AccessClaims, work_id: uuid.UUID, not_found: Callable[[], Exception]
) -> HeartState:
    """관심을 둔다. 열 수 없으면 not_found."""
    await require_opened(session, kind, viewer, work_id, not_found)
    await repository.add_heart(session, kind, viewer.user_id, work_id)
    await session.commit()
    return await current_state(session, kind, viewer, work_id)


async def take_heart(session: AsyncSession, kind: HeartKind, viewer: AccessClaims, work_id: uuid.UUID) -> HeartState:
    """관심을 거둔다. 언제나 된다."""
    await repository.remove_heart(session, kind, viewer.user_id, work_id)
    await session.commit()
    return await current_state(session, kind, viewer, work_id)


async def list_mine(
    session: AsyncSession, kind: HeartKind, viewer: AccessClaims, limit: int, offset: int
) -> tuple[list[tuple[Any, Any]], int]:
    """내 관심 작품의 한 쪽과 전체 수. 지금 열 수 있는 것만이다."""
    ratings = allowed_ratings(viewer)
    rows = await repository.list_hearted(session, kind, viewer.user_id, ratings, limit, offset)
    return rows, await repository.count_hearted(session, kind, viewer.user_id, ratings)
