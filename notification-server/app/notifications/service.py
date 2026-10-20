# notification-server/app/notifications/service.py

"""
알림을 넣는 규칙. HTTP 를 모른다. 넣는 서버가 맞는지(서명)는 부르는 쪽(router.py)이 확인했다.

  - 같은 (source, source_key) 는 한 줄이다. 같은 알림을 다시 보내면 이미 있는 줄로 답한다(EXISTING)
  - 같은 열쇠인데 내용(받는 사람, 무슨 일, 값)이 다르면 거절한다(KeyReusedError). 넣는 서버의 실수다.
    조용히 먼저 것을 돌려주면 넣는 서버는 새 알림이 들어간 줄 안다
  - 받는 사람이 그 종류를 껐으면 적지 않는다(MUTED, #525). 넣는 서버에는 받은 것과 같은 답이다(다시 보내지 않게).
    읽을 때 거르지 않고 넣을 때 거른다. 꺼 둔 동안의 알림은 다시 켜도 없다
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.mutes import service as mutes
from app.notifications import repository
from app.notifications.models import Notification
from app.notifications.schemas import NotificationIn, NotificationPut, PutStatus


class KeyReusedError(Exception):
    """같은 열쇠로 다른 알림을 넣으려 했다."""


def is_same_notification(saved: Notification, incoming: NotificationIn) -> bool:
    """이미 있는 줄이 이번에 온 알림과 같은가. 받은 시각과 읽음은 견주지 않는다."""
    return (saved.user_id, saved.kind, saved.payload) == (incoming.user_id, incoming.kind, incoming.payload)


def build_values(source: str, incoming: NotificationIn, now: datetime) -> dict:
    """테이블에 넣을 값. 받은 시각은 이 서버의 시계다. 넣는 서버가 적은 시각을 믿지 않는다."""
    return {
        'source': source,
        'source_key': incoming.source_key,
        'user_id': incoming.user_id,
        'kind': incoming.kind,
        'payload': incoming.payload,
        'created_at': now,
    }


async def put_notification(
    session: AsyncSession, source: str, incoming: NotificationIn, now: datetime
) -> NotificationPut:
    """
    알림 하나를 넣고 커밋한다. 이미 있으면 그 줄로 답한다.

    같은 열쇠의 다른 알림이면 KeyReusedError. 받는 사람이 그 종류를 껐으면 적지 않고 MUTED 다.
    """
    if await mutes.is_muted(session, incoming.user_id, incoming.kind):
        return NotificationPut(id=None, status=PutStatus.MUTED)
    new_id = await repository.insert_if_absent(session, build_values(source, incoming, now))
    if new_id is not None:
        await session.commit()
        return NotificationPut(id=new_id, status=PutStatus.CREATED)

    saved = await repository.find_by_key(session, source, incoming.source_key)
    # 넣지 못했으니 이미 있다. 이 서버는 알림을 지우지 않으므로(보관 기간이 지나기 전에는) 찾을 수 있다
    if saved is None or not is_same_notification(saved, incoming):
        raise KeyReusedError
    return NotificationPut(id=saved.id, status=PutStatus.EXISTING)
