# notification-server/app/announcements/models.py

"""
새 작품 알림을 나눠 넣은 기록의 테이블(#989). 작품 하나에 한 줄이다.

넣는 서버는 작품이 목록에 나오게 될 때마다 같은 열쇠(예: 'scenario.published:<시나리오>')로 보낸다.
이 줄이 있으면 다시 나눠 넣지 않는다. 공개를 내렸다가 다시 올려도 처음 한 번만 알린다(2026-11-04 유저 결정).
알림함의 줄은 보관 기간이 지나면 지워지지만 이 줄은 남는다. 그래서 "처음 한 번"이 기간과 상관없이 지켜진다.
제작자가 탈퇴하면 지운다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.notifications.models import KIND_MAX_LENGTH, SOURCE_KEY_MAX_LENGTH, SOURCE_MAX_LENGTH


class WorkAnnouncement(Base):
    """나눠 넣은 새 작품 알림 하나."""

    __tablename__ = 'work_announcements'

    source: Mapped[str] = mapped_column(String(SOURCE_MAX_LENGTH), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(SOURCE_KEY_MAX_LENGTH), primary_key=True)
    # 만든 사람(인증 서버의 공개 ID). 탈퇴하면 이것으로 지운다
    creator_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    kind: Mapped[str] = mapped_column(String(KIND_MAX_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
