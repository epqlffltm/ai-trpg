# shared/server-core/src/server_core/notifications/store.py

"""
보내는 작업(dispatcher.py)이 쓰는 발송함. 부를 때마다 제 세션을 열고 저장한다.

보내는 작업은 알림 서버를 부르는 동안 DB 의 연결을 쥐지 않는다.
그래서 찾는 일과 결과를 적는 일이 따로따로의 짧은 트랜잭션이다.
보내는 작업은 OutboxStore 의 모양만 안다. 공용 코드의 테스트는 DB 없이 가짜를 꽂고,
실제 쿼리는 쓰는 서버의 테스트가 본다.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server_core.notifications import repository
from server_core.notifications.models import OutgoingNotificationColumns


class OutboxStore(Protocol):
    """보내는 작업이 쓰는 발송함의 모양."""

    async def drop_stale(self, cutoff: datetime) -> int:
        """cutoff 전에 적고 아직 보내지 못한 알림을 지운다. 지운 수."""
        ...

    async def due(self, now: datetime, limit: int) -> list[OutgoingNotificationColumns]:
        """보낼 차례가 된 알림들. 먼저 적은 것부터 limit 개까지."""
        ...

    async def remove(self, notification_id: int) -> None:
        """보낸 알림을 지운다."""
        ...

    async def postpone(self, notification_id: int, next_attempt_at: datetime, reason: str) -> None:
        """보내지 못한 알림을 나중에 다시 보내게 적는다."""
        ...

    async def mark_failed(self, notification_id: int, reason: str) -> None:
        """받지 않은 알림을 실패로 적는다."""
        ...


@dataclass(frozen=True)
class SqlOutboxStore:
    """DB 의 발송함. model 은 서버의 발송함 표다."""

    session_factory: async_sessionmaker[AsyncSession]
    model: type[OutgoingNotificationColumns]

    async def drop_stale(self, cutoff: datetime) -> int:
        """cutoff 전에 적고 아직 보내지 못한 알림을 지우고 저장한다. 지운 수."""
        async with self.session_factory() as session:
            dropped = await repository.drop_stale(session, self.model, cutoff)
            await session.commit()
            return dropped

    async def due(self, now: datetime, limit: int) -> list[OutgoingNotificationColumns]:
        """보낼 차례가 된 알림들. 잠그지 않는다."""
        async with self.session_factory() as session:
            return await repository.find_due(session, self.model, now, limit)

    async def remove(self, notification_id: int) -> None:
        """보낸 알림을 지우고 저장한다."""
        async with self.session_factory() as session:
            await repository.remove(session, self.model, notification_id)
            await session.commit()

    async def postpone(self, notification_id: int, next_attempt_at: datetime, reason: str) -> None:
        """보내지 못한 알림을 next_attempt_at 에 다시 보내게 적고 저장한다."""
        async with self.session_factory() as session:
            await repository.postpone(session, self.model, notification_id, next_attempt_at, reason)
            await session.commit()

    async def mark_failed(self, notification_id: int, reason: str) -> None:
        """받지 않은 알림을 실패로 적고 저장한다."""
        async with self.session_factory() as session:
            await repository.mark_failed(session, self.model, notification_id, reason)
            await session.commit()
