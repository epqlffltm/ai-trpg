# notification-server/app/announcements/repository.py

"""
새 작품 알림의 DB 접근(#989). SQL 은 이 파일에만 있다. 커밋하지 않는다.

팔로워마다 알림을 한 문장(INSERT … SELECT)으로 넣는다. 팔로워를 파이썬으로 읽어 하나씩 넣지 않는다.
팔로워마다의 열쇠는 '<작품의 열쇠>:<팔로워>' 다. 같은 문장이 두 번 돌아도 알림함의 열쇠가 겹쳐 한 줄씩이다.
"""

import uuid
from datetime import datetime

from server_core.database import affected_rows
from sqlalchemy import String, cast, delete, exists, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.announcements.models import WorkAnnouncement
from app.follows.models import CreatorFollow
from app.notifications.models import Notification, NotificationMute


async def record_announcement(
    session: AsyncSession, source: str, source_key: str, creator_id: uuid.UUID, kind: str, now: datetime
) -> bool:
    """나눠 넣은 기록을 적는다. 이미 있으면 적지 않고 거짓이다. 동시에 두 번 와도 하나만 참이다."""
    statement = (
        insert(WorkAnnouncement)
        .values(source=source, source_key=source_key, creator_id=creator_id, kind=kind, created_at=now)
        .on_conflict_do_nothing(index_elements=['source', 'source_key'])
        .returning(WorkAnnouncement.source_key)
    )
    return await session.scalar(statement) is not None


async def fan_out(
    session: AsyncSession,
    source: str,
    source_key: str,
    creator_id: uuid.UUID,
    kind: str,
    payload: dict,
    now: datetime,
    skip_muted: bool,
) -> int:
    """제작자의 팔로워마다 알림을 넣는다. skip_muted 면 그 종류를 끈 팔로워는 뺀다. 넣은 수다."""
    follower = CreatorFollow.follower_id
    followers = select(
        follower,
        literal(source),
        func.concat(f'{source_key}:', cast(follower, String)),
        literal(kind),
        literal(payload, JSONB),
        literal(now),
    ).where(CreatorFollow.creator_id == creator_id)
    if skip_muted:
        muted = exists().where(NotificationMute.user_id == follower, NotificationMute.kind == kind)
        followers = followers.where(~muted)
    statement = (
        insert(Notification)
        .from_select(['user_id', 'source', 'source_key', 'kind', 'payload', 'created_at'], followers)
        .on_conflict_do_nothing(constraint='uq_notifications_source_key')
    )
    return affected_rows(await session.execute(statement))


async def delete_announcements(session: AsyncSession, creator_id: uuid.UUID) -> int:
    """그 제작자의 기록을 지운다. 탈퇴할 때 부른다. 지운 수다."""
    return affected_rows(
        await session.execute(delete(WorkAnnouncement).where(WorkAnnouncement.creator_id == creator_id))
    )
