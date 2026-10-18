# notification-server/app/inbox/repository.py

"""
알림함을 읽고 읽음을 적는 SQL. 규칙을 모른다. 모든 질의가 받는 사람(user_id)으로 묶인다. 남의 알림에 닿지 않는다.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification


async def list_page(
    session: AsyncSession, user_id: uuid.UUID, before: int | None, limit: int
) -> Sequence[Notification]:
    """
    이 사람의 알림을 최근 것부터 limit 개 읽는다. before 가 있으면 그 번호보다 작은 것만이다.

    색인(user_id, id DESC)을 그대로 따라 읽는다. 쪽을 몇 개 넘겨도 앞의 줄을 세며 건너뛰지 않는다(OFFSET 이 아니다).
    """
    statement = select(Notification).where(Notification.user_id == user_id)
    if before is not None:
        statement = statement.where(Notification.id < before)
    statement = statement.order_by(Notification.id.desc()).limit(limit)
    return (await session.scalars(statement)).all()


async def count_unread(session: AsyncSession, user_id: uuid.UUID) -> int:
    """이 사람의 읽지 않은 알림의 수. 읽지 않은 줄만 담는 색인(ix_notifications_unread)을 쓴다."""
    statement = select(func.count()).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    return await session.scalar(statement)


async def mark_one_read(session: AsyncSession, user_id: uuid.UUID, notification_id: int, now: datetime) -> bool:
    """
    이 사람의 알림 하나를 읽음으로 한다. 이미 읽었으면 처음 읽은 시각을 그대로 둔다.

    그 번호가 이 사람의 것이면 True, 없거나 남의 것이면 False 다.
    """
    statement = (
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user_id)
        .values(read_at=func.coalesce(Notification.read_at, now))
        .returning(Notification.id)
    )
    return await session.scalar(statement) is not None


async def find_own(session: AsyncSession, user_id: uuid.UUID, notification_id: int) -> Notification | None:
    """이 사람의 알림 하나. 없거나 남의 것이면 None 이다."""
    statement = select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    return await session.scalar(statement)


async def mark_read_up_to(session: AsyncSession, user_id: uuid.UUID, up_to: int, now: datetime) -> int:
    """이 사람의 읽지 않은 알림 중 번호가 up_to 이하인 것을 읽음으로 한다. 읽음이 된 수를 돌려준다."""
    statement = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None), Notification.id <= up_to)
        .values(read_at=now)
    )
    result = await session.execute(statement)
    return result.rowcount
