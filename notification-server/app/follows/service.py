# notification-server/app/follows/service.py

"""
제작자 팔로우의 규칙(#989). HTTP 를 모른다. 누가 하는지는 부르는 쪽(router.py)이 토큰에서 꺼냈다.

  - 자기 자신은 팔로우하지 않는다(FollowSelfError)
  - 한 사람이 팔로우하는 제작자는 FOLLOW_MAX_PER_USER(기본 1,000) 명까지다. 넘으면 FollowLimitError 다.
    이미 팔로우하는 제작자를 다시 팔로우하는 것은 상한에 걸리지 않는다
  - 팔로우하기와 끊기는 몇 번 해도 같다
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.follows import repository
from app.follows.schemas import Followed, FollowerCount, FollowingPage, FollowState


class FollowSelfError(Exception):
    """자기 자신을 팔로우하려 했다."""


class FollowLimitError(Exception):
    """팔로우할 수 있는 제작자의 수를 넘었다."""


async def state_of(session: AsyncSession, follower_id: uuid.UUID, creator_id: uuid.UUID) -> FollowState:
    """내가 팔로우하는지와 그 제작자의 팔로워 수."""
    return FollowState(
        following=await repository.is_following(session, follower_id, creator_id),
        follower_count=await repository.count_followers(session, creator_id),
    )


async def follow(
    session: AsyncSession, follower_id: uuid.UUID, creator_id: uuid.UUID, limit: int, now: datetime
) -> FollowState:
    """팔로우하고 커밋한다. 자기 자신이면 FollowSelfError, 상한을 넘으면 FollowLimitError."""
    if follower_id == creator_id:
        raise FollowSelfError
    await repository.lock_follower(session, follower_id)
    already = await repository.is_following(session, follower_id, creator_id)
    if not already and await repository.count_following(session, follower_id) >= limit:
        raise FollowLimitError
    await repository.insert_follow(session, follower_id, creator_id, now)
    await session.commit()
    return await state_of(session, follower_id, creator_id)


async def unfollow(session: AsyncSession, follower_id: uuid.UUID, creator_id: uuid.UUID) -> FollowState:
    """팔로우를 끊고 커밋한다."""
    await repository.delete_follow(session, follower_id, creator_id)
    await session.commit()
    return await state_of(session, follower_id, creator_id)


async def followers_of(session: AsyncSession, creator_id: uuid.UUID) -> FollowerCount:
    """그 제작자의 팔로워 수."""
    return FollowerCount(follower_count=await repository.count_followers(session, creator_id))


async def following_page(session: AsyncSession, follower_id: uuid.UUID, limit: int, offset: int) -> FollowingPage:
    """내 팔로잉의 한 쪽과 전체 수."""
    rows = await repository.list_following(session, follower_id, limit, offset)
    return FollowingPage(
        items=[Followed(creator_id=creator_id, followed_at=at) for creator_id, at in rows],
        total=await repository.count_following(session, follower_id),
    )
