# notification-server/app/mutes/repository.py

"""
사용자가 끈 알림의 종류(notification_mutes)에 닿는 SQL. 규칙을 모른다. 끌 수 있는 종류인지는 service.py 가 본다.
모든 질의가 사람(user_id)으로 묶인다. 남의 설정에 닿지 않는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import NotificationMute


async def is_muted(session: AsyncSession, user_id: uuid.UUID, kind: str) -> bool:
    """이 사람이 이 종류를 껐는가. 기본 키(user_id, kind)로 한 줄을 찾는다."""
    statement = select(exists().where(NotificationMute.user_id == user_id, NotificationMute.kind == kind))
    return bool(await session.scalar(statement))


async def list_muted(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """이 사람이 끈 종류들."""
    statement = select(NotificationMute.kind).where(NotificationMute.user_id == user_id)
    return set((await session.scalars(statement)).all())


async def insert_mute(session: AsyncSession, user_id: uuid.UUID, kind: str, now: datetime) -> None:
    """
    이 종류를 끈다. 이미 꺼져 있으면 아무것도 하지 않는다(처음 끈 시각 그대로).

    먼저 찾아보고 넣지 않는다. 같은 요청이 동시에 두 번 와도 DB 가 하나만 넣는다.
    """
    statement = (
        insert(NotificationMute)
        .values(user_id=user_id, kind=kind, created_at=now)
        .on_conflict_do_nothing(index_elements=[NotificationMute.user_id, NotificationMute.kind])
    )
    await session.execute(statement)


async def delete_mute(session: AsyncSession, user_id: uuid.UUID, kind: str) -> None:
    """이 종류를 다시 켠다. 켜져 있으면(줄이 없으면) 아무것도 하지 않는다."""
    statement = delete(NotificationMute).where(NotificationMute.user_id == user_id, NotificationMute.kind == kind)
    await session.execute(statement)
