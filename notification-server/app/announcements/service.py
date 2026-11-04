# notification-server/app/announcements/service.py

"""
새 작품 알림을 나눠 넣는 규칙(#989). HTTP 를 모른다. 넣는 서버가 맞는지(서명)와 표(catalog)는 부르는 쪽이 봤다.

받는 알림의 user_id 는 받는 사람이 아니라 만든 사람이다(표의 audience 가 followers 인 종류).
  - 처음 온 열쇠면 기록을 적고 그때의 팔로워마다 알림을 넣는다(CREATED). 팔로워가 없어도 기록은 남는다
  - 이미 기록이 있으면 아무것도 넣지 않는다(EXISTING). 다시 보낸 것이거나 공개를 내렸다가 다시 올린 것이다
  - 그 종류를 끈 팔로워에게는 넣지 않는다
기록과 알림은 한 트랜잭션이다. 넣다가 실패하면 기록도 남지 않아 넣는 서버가 다시 보낼 때 다시 한다.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.announcements import repository
from app.notifications import catalog
from app.notifications.schemas import NotificationIn, NotificationPut, PutStatus


@dataclass(frozen=True)
class Announced:
    """나눠 넣은 결과. 넣는 서버에 줄 답과 넣은 알림의 수(로그에만 쓴다)."""

    put: NotificationPut
    recipients: int


async def announce(session: AsyncSession, source: str, incoming: NotificationIn, now: datetime) -> Announced:
    """만든 사람의 팔로워에게 새 작품 알림을 넣고 커밋한다. 처음 한 번만이다."""
    creator_id = incoming.user_id
    recorded = await repository.record_announcement(
        session, source, incoming.source_key, creator_id, incoming.kind, now
    )
    if not recorded:
        return Announced(NotificationPut(id=None, status=PutStatus.EXISTING), 0)
    recipients = await repository.fan_out(
        session,
        source,
        incoming.source_key,
        creator_id,
        incoming.kind,
        incoming.payload,
        now,
        skip_muted=catalog.is_mutable(incoming.kind),
    )
    await session.commit()
    return Announced(NotificationPut(id=None, status=PutStatus.CREATED), recipients)
