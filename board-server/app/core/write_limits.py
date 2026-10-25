# board-server/app/core/write_limits.py

"""
글과 댓글을 얼마나 자주 쓸 수 있는가, 신고를 얼마나 자주 할 수 있는가.

도배를 막는 것이 목적이다. 사람이 쓰는 속도로는 닿기 어렵고, 프로그램으로 쏟아붓는 것은 금방 걸리는 선으로 잡았다.
숫자를 설정(환경 변수)으로 빼지 않았다. 바꿀 일이 드물고, 잘못 넣으면 제한이 꺼지거나 아무도 쓰지 못한다.

  - 지운 글과 댓글도 센다. 쓰고 지우기를 되풀이해 한도를 피하지 못한다
  - 운영자는 걸리지 않는다. 공지를 연달아 올려야 할 때가 있다
  - 걸리면 429 와 기다릴 초(retry_after, Retry-After)다. 가장 오래된 것이 창을 벗어날 때까지 남은 시간이다
"""

import math
from dataclasses import dataclass

from fastapi import status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Actor
from app.core.errors import ApiError


@dataclass(frozen=True)
class WriteLimit:
    """정해 둔 시간(window_seconds) 안에 쓸 수 있는 수(max)와 걸렸을 때의 문장."""

    table: str
    owner: str
    window_seconds: int
    max: int
    detail: str


# 글: 10분에 5개
POST_LIMIT = WriteLimit('posts', 'author_id', 10 * 60, 5, '글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.')
# 댓글과 답글: 1분에 10개
COMMENT_LIMIT = WriteLimit(
    'comments', 'author_id', 60, 10, '댓글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.'
)
# 신고: 1시간에 20건. 한 사람이 신고로 운영자의 목록을 덮지 못하게 한다
REPORT_LIMIT = WriteLimit(
    'reports', 'reporter_id', 60 * 60, 20, '신고를 너무 자주 하고 있습니다. 잠시 후 다시 시도해 주세요.'
)


def retry_after_seconds(remaining: object) -> int:
    """기다릴 초를 올림한 1 이상의 정수로. "0초 뒤에 다시"는 지금 바로 다시 보내라는 말이 된다."""
    try:
        seconds = math.ceil(float(remaining))  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return 1
    return seconds if seconds >= 1 else 1


def remaining_query(limit: WriteLimit):
    """
    창 안에서 max 번째로 최근에 쓴 것이 창을 벗어날 때까지 남은 초. 그만큼 쓰지 않았으면 행이 없다.

    표와 칸의 이름은 코드에 정해 둔 것만 쓴다(사용자의 값이 아니다).
    """
    return text(
        f"""
        SELECT EXTRACT(EPOCH FROM (created_at + make_interval(secs => :window) - now())) AS remaining
          FROM {limit.table}
         WHERE {limit.owner} = :user_id
           AND created_at > now() - make_interval(secs => :window)
         ORDER BY created_at DESC
        OFFSET :skip LIMIT 1
        """
    )


async def seconds_until_allowed(session: AsyncSession, limit: WriteLimit, actor: Actor) -> int | None:
    """한도에 걸렸으면 기다릴 초, 아니면 None 이다."""
    row = await session.execute(
        remaining_query(limit), {'window': limit.window_seconds, 'user_id': actor.user_id, 'skip': limit.max - 1}
    )
    remaining = row.scalar_one_or_none()
    return None if remaining is None else retry_after_seconds(remaining)


async def ensure_within(session: AsyncSession, limit: WriteLimit, actor: Actor) -> None:
    """한도 안이면 지나가고, 걸렸으면 429 를 던진다. 운영자는 보지 않는다."""
    if actor.is_operator:
        return
    retry_after = await seconds_until_allowed(session, limit, actor)
    if retry_after is not None:
        raise ApiError(status.HTTP_429_TOO_MANY_REQUESTS, limit.detail, retry_after=retry_after)
