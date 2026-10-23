# shared/server-core/src/server_core/notifications/repository.py

"""
발송함의 쿼리. 저장(commit)은 부른 쪽이 한다. model 은 서버의 발송함 표(models.py 의 칸을 물려받은 것)다.

바꾸는 쿼리는 "아직 기다리는 줄일 때만" 바꾼다. 서버 둘이 같은 줄을 보내도 한쪽의 결과가 다른 쪽의 것을 덮어
지운 줄을 되살리거나 받지 않은 줄을 다시 기다리게 하지 않는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server_core.notifications.models import OutboxStatus, OutgoingNotificationColumns

type Outbox = type[OutgoingNotificationColumns]


def is_pending(model: Outbox):
    """기다리는 줄이라는 조건."""
    return model.status == OutboxStatus.PENDING


def put[T: OutgoingNotificationColumns](
    session: AsyncSession, model: type[T], user_id: uuid.UUID, kind: str, source_key: str, payload: dict
) -> T:
    """발송함에 알림 하나를 적는다. 저장하지 않는다. 바로 보낼 차례다."""
    notification = model(user_id=user_id, kind=kind, source_key=source_key, payload=payload)
    session.add(notification)
    return notification


async def find_due[T: OutgoingNotificationColumns](
    session: AsyncSession, model: type[T], now: datetime, limit: int
) -> list[T]:
    """보낼 차례가 된 알림들. 먼저 적은 것부터다. 잠그지 않는다."""
    query = (
        select(model)
        .where(is_pending(model), or_(model.next_attempt_at.is_(None), model.next_attempt_at <= now))
        .order_by(model.id)
        .limit(limit)
    )
    return list(await session.scalars(query))


async def remove(session: AsyncSession, model: Outbox, notification_id: int) -> None:
    """보낸 알림을 지운다. 기록은 알림 서버에 있다."""
    await session.execute(delete(model).where(model.id == notification_id))


async def postpone(
    session: AsyncSession, model: Outbox, notification_id: int, next_attempt_at: datetime, reason: str
) -> None:
    """보내지 못한 알림을 next_attempt_at 에 다시 보내게 적는다. 보내지 못한 횟수가 하나 는다."""
    query = (
        update(model)
        .where(model.id == notification_id, is_pending(model))
        .values(attempts=model.attempts + 1, next_attempt_at=next_attempt_at, last_error=reason)
    )
    await session.execute(query)


async def mark_failed(session: AsyncSession, model: Outbox, notification_id: int, reason: str) -> None:
    """알림 서버가 받지 않은 알림을 실패로 적는다. 다시 보내지 않는다."""
    query = (
        update(model)
        .where(model.id == notification_id, is_pending(model))
        .values(status=OutboxStatus.FAILED, last_error=reason)
    )
    await session.execute(query)


async def drop_stale(session: AsyncSession, model: Outbox, cutoff: datetime) -> int:
    """cutoff 전에 적고 아직 보내지 못한 알림을 지운다. 지운 수."""
    result = await session.execute(delete(model).where(is_pending(model), model.created_at < cutoff))
    return result.rowcount


async def drop_for_user(session: AsyncSession, model: Outbox, user_id: uuid.UUID) -> None:
    """그 사람에게 아직 보내지 않은 알림을 지운다(탈퇴). 알림 서버도 그 사람의 알림함을 지운다."""
    await session.execute(delete(model).where(model.user_id == user_id))
