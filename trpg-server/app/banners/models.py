# trpg-server/app/banners/models.py

"""
홍보 배너의 테이블 모델(#994). 운영자가 공개된 시나리오 하나를 골라 첫 화면의 넘기는 배너에 건다.

배너에 따로 그림과 글을 두지 않는다. 시나리오의 공개 정보(제목, 한 줄 소개, 장르)를 그대로 보인다.
시나리오의 공개를 내리거나, 지우거나, 볼 수 없는 등급이면 저절로 빠진다(읽을 때 공개 목록의 조건으로 거른다).
시나리오의 행이 지워지면 배너도 지워진다(외래 키의 CASCADE). 캐릭터와 세계관의 배너는 asset 서버가 가진다.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 차례의 가장 큰 값. 작은 것이 먼저다
BANNER_MAX_POSITION = 999


class Banner(Base):
    """걸어 둔 배너 하나. 기간(starts_at ~ ends_at) 안에만 보인다. ends_at 이 비어 있으면 내릴 때까지다."""

    __tablename__ = 'banners'
    __table_args__ = (
        CheckConstraint(f'position >= 0 AND position <= {BANNER_MAX_POSITION}', name='position_range'),
        CheckConstraint('ends_at IS NULL OR starts_at < ends_at', name='period_order'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('scenarios.asset_id', ondelete='CASCADE'), index=True)
    # 배너의 차례. 작은 것이 먼저고, 같으면 먼저 건 것이 먼저다
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 건 운영자. 토큰의 sub 다
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
