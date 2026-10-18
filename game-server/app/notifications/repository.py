# game-server/app/notifications/repository.py

"""
발송함의 쿼리. 저장(commit)은 부른 쪽이 한다.

바꾸는 쿼리는 "아직 기다리는 줄일 때만" 바꾼다. 서버 둘이 같은 줄을 보내도 한쪽의 결과가 다른 쪽의 것을 덮어
지운 줄을 되살리거나 받지 않은 줄을 다시 기다리게 하지 않는다.
"""

from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import OutboxStatus, OutgoingNotification


def is_pending():
    """기다리는 줄이라는 조건."""
    return OutgoingNotification.status == OutboxStatus.PENDING


async def find_due(session: AsyncSession, now: datetime, limit: int) -> list[OutgoingNotification]:
    """보낼 차례가 된 알림들. 먼저 적은 것부터다. 잠그지 않는다."""
    query = (
        select(OutgoingNotification)
        .where(
            is_pending(),
            or_(OutgoingNotification.next_attempt_at.is_(None), OutgoingNotification.next_attempt_at <= now),
        )
        .order_by(OutgoingNotification.id)
        .limit(limit)
    )
    return list(await session.scalars(query))


async def remove(session: AsyncSession, notification_id: int) -> None:
    """보낸 알림을 지운다. 기록은 알림 서버에 있다."""
    await session.execute(delete(OutgoingNotification).where(OutgoingNotification.id == notification_id))


async def postpone(session: AsyncSession, notification_id: int, next_attempt_at: datetime, reason: str) -> None:
    """보내지 못한 알림을 next_attempt_at 에 다시 보내게 적는다. 보내지 못한 횟수가 하나 는다."""
    query = (
        update(OutgoingNotification)
        .where(OutgoingNotification.id == notification_id, is_pending())
        .values(attempts=OutgoingNotification.attempts + 1, next_attempt_at=next_attempt_at, last_error=reason)
    )
    await session.execute(query)


async def mark_failed(session: AsyncSession, notification_id: int, reason: str) -> None:
    """알림 서버가 받지 않은 알림을 실패로 적는다. 다시 보내지 않는다."""
    query = (
        update(OutgoingNotification)
        .where(OutgoingNotification.id == notification_id, is_pending())
        .values(status=OutboxStatus.FAILED, last_error=reason)
    )
    await session.execute(query)


async def drop_stale(session: AsyncSession, cutoff: datetime) -> int:
    """cutoff 전에 적고 아직 보내지 못한 알림을 지운다. 지운 수."""
    query = delete(OutgoingNotification).where(is_pending(), OutgoingNotification.created_at < cutoff)
    result = await session.execute(query)
    return result.rowcount
