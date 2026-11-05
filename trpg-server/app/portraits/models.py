# trpg-server/app/portraits/models.py

"""
제작자가 올린 캐릭터 그림의 기록(portraits, #983).

  - 그림은 asset 서버의 그림이다. 이 서버가 올린 사람의 토큰으로 맡겨서 주인은 올린 사람이고, 맡긴 서버는 이 서버다.
    그래서 이 서버가 서명만으로 바이트를 받아(app/asset_server/client.py 의 fetch_kept) 볼 수 있는 사람에게 내준다
  - 기록의 id 는 asset 의 그림 id 그대로다. 프리젠이 이 id 를 가리킨다(시나리오의 pregens[].image_id)
  - 이 기록이 있어야 "이 서버에 올린 그림"이다. asset 의 다른 그림(장면 그림, chat 의 그림)은 프리젠에 붙이지 못한다
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Portrait(Base):
    """올린 캐릭터 그림 하나."""

    __tablename__ = 'portraits'
    __table_args__ = (
        # 올린 사람의 그림들을 최근 것부터 찾는다(그림을 고르는 목록)
        Index('ix_portraits_owner_created', 'owner_id', 'created_at'),
    )

    # asset 서버의 그림 id
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # 올린 사람. 인증 서버의 public_id 다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
