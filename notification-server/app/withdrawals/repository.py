# notification-server/app/withdrawals/repository.py

"""
탈퇴한 사람의 줄을 지우는 SQL(#603). 규칙을 모른다. 무엇을 지울지는 service.py 가 정한다.
모든 문장이 사람(user_id)으로 묶인다. 남의 줄에 닿지 않는다.
"""

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification, NotificationMute


async def delete_notifications(session: AsyncSession, user_id: uuid.UUID) -> int:
    """그 사람의 알림을 모두 지운다. 지운 줄의 수를 돌려준다. 색인(user_id, id)으로 찾는다."""
    result = await session.execute(delete(Notification).where(Notification.user_id == user_id))
    return result.rowcount


async def delete_mutes(session: AsyncSession, user_id: uuid.UUID) -> int:
    """그 사람이 끈 알림의 종류를 모두 지운다. 지운 줄의 수를 돌려준다. 기본 키(user_id, kind)의 앞쪽으로 찾는다."""
    result = await session.execute(delete(NotificationMute).where(NotificationMute.user_id == user_id))
    return result.rowcount
