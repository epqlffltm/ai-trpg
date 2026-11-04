# notification-server/app/follows/models.py

"""
제작자 팔로우의 테이블(#989). 한 사람이 제작자 하나를 팔로우하면 한 줄이다.

제작자는 인증 서버의 공개 ID 다. 이 서버는 그런 사람이 있는지 모른다(실행 중에 인증 서버를 부르지 않는다).
없는 공개 ID 를 팔로우해도 알림이 오지 않을 뿐이다. 탈퇴하면 팔로우한 것과 받은 팔로우를 모두 지운다.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CreatorFollow(Base):
    """팔로우 하나. 자기 자신은 팔로우하지 않는다."""

    __tablename__ = 'creator_follows'
    __table_args__ = (
        CheckConstraint('follower_id <> creator_id', name='not_self'),
        # 내 팔로잉: 최근에 한 것부터
        Index('ix_creator_follows_follower_created', 'follower_id', 'created_at'),
    )

    # 팔로우한 사람. 토큰의 sub(인증 서버의 public_id)다
    follower_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # 팔로우한 제작자. 팔로워의 수와 알림을 나눠 넣을 때 이것으로 찾는다
    creator_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
