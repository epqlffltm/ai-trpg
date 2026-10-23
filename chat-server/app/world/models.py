# chat-server/app/world/models.py

"""
말마다의 상태(message_states). 상태가 바뀐 말(행동 말)에만 행이 있다. 나머지 말은 부모의 상태를 따른다.

매번 상태 전체를 담는다(바뀐 것만 담아 다시 쌓는 방식이 아니다). 장소 하나와 소지품 수십 개라 작고, 읽기가 단순하다.
말을 지우면(대화를 지우면) 함께 지워진다.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 장소와 물건의 id 의 길이. asset 서버의 판과 같다
KEY_MAX_LENGTH = 40


class MessageState(Base):
    """
    그 말 뒤의 상태. place 는 지금 있는 장소의 id, minutes 는 흐른 시간(분), visited 는 가 본 장소들,
    outfit 은 상대가 입은 옷들이다.
    """

    __tablename__ = 'message_states'
    __table_args__ = (
        CheckConstraint('minutes >= 0', name='minutes_not_negative'),
        CheckConstraint('affection IS NULL OR affection BETWEEN 0 AND 100', name='affection_in_range'),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('messages.id', ondelete='CASCADE'), primary_key=True)
    place: Mapped[str | None] = mapped_column(String(KEY_MAX_LENGTH), default=None)
    minutes: Mapped[int] = mapped_column(Integer)
    # 가진 물건들 [{"item", "count"}]
    inventory: Mapped[list[dict]] = mapped_column(JSONB)
    visited: Mapped[list[str]] = mapped_column(ARRAY(String(KEY_MAX_LENGTH)))
    # 상대가 입은 옷들(사용자가 건넨 옷)의 물건 id
    outfit: Mapped[list[str]] = mapped_column(ARRAY(String(KEY_MAX_LENGTH)), default=list, server_default='{}')
    # 호감도(0~100, 판에 호감도가 없으면 null)와 이 가지에서 걸린 "처음 한 번만" 규칙의 id
    affection: Mapped[int | None] = mapped_column(Integer, default=None)
    fired: Mapped[list[str]] = mapped_column(ARRAY(String(KEY_MAX_LENGTH)), default=list, server_default='{}')
    # 이 가지에서 나온 이벤트 씬의 id(나온 차례, app/world/scenes.py, #669). 한 가지에서 한 번만 나온다
    shown: Mapped[list[str]] = mapped_column(ARRAY(String(KEY_MAX_LENGTH)), default=list, server_default='{}')
