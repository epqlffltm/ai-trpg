# asset-server/app/stats/models.py

"""
작품마다의 시작 수의 테이블 모델(#985). chat 서버와 story 서버에서 받아 온 것이다.

작품의 외래 키를 걸지 않는다. 다른 서버가 센 수라 지운 작품의 수도 올 수 있다. 읽을 때 공개 목록의 조건과 잇는다.
받을 때마다 그 종류의 줄을 통째로 바꾼다(빠진 작품은 지워진다).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkKind(enum.StrEnum):
    """무엇의 수인가. 캐릭터(chat 의 대화)와 세계관(story 의 세션)이다."""

    CHARACTER = 'character'
    WORLD = 'world'


class WorkStarts(Base):
    """작품 하나의 시작 수. recent 는 최근 recent_days 일 동안의 수다."""

    __tablename__ = 'work_starts'
    __table_args__ = (
        CheckConstraint("kind IN ('character', 'world')", name='kind_allowed'),
        CheckConstraint('total >= recent AND recent >= 0', name='counts_ordered'),
    )

    kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    work_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    total: Mapped[int] = mapped_column(Integer)
    recent: Mapped[int] = mapped_column(Integer)
    # "최근"의 날 수(그 서버가 정한다). 지금은 7일이다
    recent_days: Mapped[int] = mapped_column(Integer)
    # 받아 온 시각. 같은 종류의 줄은 모두 같다
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
