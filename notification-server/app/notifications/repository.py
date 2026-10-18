# notification-server/app/notifications/repository.py

"""
알림함 테이블에 닿는 SQL. 규칙을 모른다. 무엇을 넣고 찾을지는 service.py 가 정한다.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification


async def insert_if_absent(session: AsyncSession, values: dict) -> int | None:
    """
    알림 한 줄을 넣는다. 같은 (source, source_key) 가 이미 있으면 넣지 않는다.

    넣었으면 새 번호, 이미 있었으면 None 이다. 동시에 같은 열쇠가 두 번 와도 DB 가 하나만 넣는다.
    먼저 찾아보고 없으면 넣는 방식은 동시에 온 둘이 모두 "없다"를 보고 둘 다 넣으려 한다.
    """
    statement = (
        insert(Notification)
        .values(**values)
        .on_conflict_do_nothing(constraint='uq_notifications_source_key')
        .returning(Notification.id)
    )
    return await session.scalar(statement)


async def find_by_key(session: AsyncSession, source: str, source_key: str) -> Notification | None:
    """넣은 서버와 열쇠로 알림을 찾는다. 없으면 None 이다."""
    statement = select(Notification).where(Notification.source == source, Notification.source_key == source_key)
    return await session.scalar(statement)
