# asset-server/app/banners/models.py

"""
홍보 배너의 테이블 모델(#994). 운영자가 공개된 캐릭터나 세계관 하나를 골라 첫 화면의 넘기는 배너에 건다.

배너에 따로 그림과 글을 두지 않는다. 작품의 마지막 판(이름, 대표 그림, 태그)을 그대로 보인다.
비공개로 돌리거나, 숨기거나, 볼 수 없는 등급이면 저절로 빠진다(읽을 때 공개 목록의 조건으로 거른다).
작품을 지우면 배너도 지워진다(외래 키의 CASCADE). 시나리오의 배너는 trpg-server 가 가진다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 차례의 가장 큰 값. 작은 것이 먼저다(trpg-server 와 같다)
BANNER_MAX_POSITION = 999


class BannerKind(enum.StrEnum):
    """무엇을 거는가."""

    CHARACTER = 'character'
    WORLD = 'world'


class Banner(Base):
    """
    걸어 둔 배너 하나. 캐릭터나 세계관 가운데 꼭 하나를 가리킨다.

    기간 안에만 보인다. ends_at 이 비면 내릴 때까지다.
    """

    __tablename__ = 'banners'
    __table_args__ = (
        CheckConstraint('num_nonnulls(character_id, world_id) = 1', name='one_target'),
        CheckConstraint(f'position >= 0 AND position <= {BANNER_MAX_POSITION}', name='position_range'),
        CheckConstraint('ends_at IS NULL OR starts_at < ends_at', name='period_order'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    character_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('characters.id', ondelete='CASCADE'), index=True)
    world_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('worlds.id', ondelete='CASCADE'), index=True)
    # 배너의 차례. 작은 것이 먼저고, 같으면 먼저 건 것이 먼저다
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 건 운영자. 토큰의 sub 다
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def kind(self) -> BannerKind:
        """무엇을 건 배너인가."""
        return BannerKind.CHARACTER if self.character_id is not None else BannerKind.WORLD

    @property
    def target_id(self) -> uuid.UUID:
        """건 작품의 ID."""
        return self.character_id or self.world_id  # type: ignore[return-value]
