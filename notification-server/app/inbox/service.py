# notification-server/app/inbox/service.py

"""
알림함의 규칙. HTTP 를 모른다. 누구의 알림함인지는 부르는 쪽(router.py)이 토큰에서 꺼냈다.

  - 내 알림만 보인다. 남의 알림 번호를 대면 없는 것과 같다(NotificationNotFoundError)
  - 읽음은 처음 읽은 시각이다. 다시 읽음으로 해도 시각이 바뀌지 않는다
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.inbox import repository
from app.inbox.schemas import NotificationPage, NotificationView, ReadAllResult, UnreadCount, view_of


class NotificationNotFoundError(Exception):
    """그런 알림이 없거나 남의 것이다. 둘을 나누지 않는다(남의 알림이 있는지 알리지 않는다)."""


async def read_page(session: AsyncSession, user_id: uuid.UUID, before: int | None, limit: int) -> NotificationPage:
    """
    알림함의 한 쪽을 읽는다.

    한 개를 더 읽어 다음 쪽이 있는지 안다. 꼭 limit 개가 남았을 때 빈 쪽을 한 번 더 부르지 않게 한다.
    """
    rows = await repository.list_page(session, user_id, before, limit + 1)
    items = [view_of(row) for row in rows[:limit]]
    next_before = items[-1].id if len(rows) > limit else None
    return NotificationPage(items=items, next_before=next_before)


async def read_unread_count(session: AsyncSession, user_id: uuid.UUID) -> UnreadCount:
    """읽지 않은 알림의 수."""
    return UnreadCount(unread=await repository.count_unread(session, user_id))


async def mark_read(session: AsyncSession, user_id: uuid.UUID, notification_id: int, now: datetime) -> NotificationView:
    """알림 하나를 읽음으로 하고 커밋한다. 그 알림을 돌려준다. 없거나 남의 것이면 NotificationNotFoundError."""
    if not await repository.mark_one_read(session, user_id, notification_id, now):
        raise NotificationNotFoundError
    await session.commit()
    notification = await repository.find_own(session, user_id, notification_id)
    if notification is None:
        # 커밋과 다시 읽기 사이에 지워졌다(보관 기간의 정리). 없는 것과 같다
        raise NotificationNotFoundError
    return view_of(notification)


async def mark_all_read(session: AsyncSession, user_id: uuid.UUID, up_to: int, now: datetime) -> ReadAllResult:
    """up_to 번호까지의 읽지 않은 알림을 모두 읽음으로 하고 커밋한다."""
    count = await repository.mark_read_up_to(session, user_id, up_to, now)
    await session.commit()
    return ReadAllResult(read=count)
