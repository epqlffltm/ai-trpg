# asset-server/app/shortcuts/models.py

"""
내 단축어의 테이블(#981). 사람마다 한 줄이고, 단축어의 목록(JSONB)을 통째로 담는다.

목록은 20개까지로 작고, 늘 통째로 읽고 바꾼다(고르는 목록과 차례가 그대로다). 그래서 단축어마다 줄을 나누지 않는다.
모양은 schemas.Shortcut 이 정한다. 탈퇴하면 지운다(app/withdrawal/service.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserShortcuts(Base):
    """한 사람의 단축어들. 줄이 없으면 아직 적지 않은 것이다(빈 목록)."""

    __tablename__ = 'user_shortcuts'

    # 주인. 인증 서버의 public_id 다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    items: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
