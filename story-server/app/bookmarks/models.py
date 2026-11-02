# story-server/app/bookmarks/models.py

"""
책갈피의 테이블. 말 하나에 하나다(다시 달면 메모만 바뀐다).

말이나 세션의 행이 지워지면 함께 지워진다(CASCADE, 탈퇴). 세션을 지우면(지운 시각을 적으면) 서비스가 따로 지운다.
모델에는 가지 않는다. 사람이 다시 찾아가려고 다는 표시다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 메모의 길이(글자)와 세션 하나의 책갈피 수의 상한
BOOKMARK_NOTE_MAX_CHARS = 100
BOOKMARKS_PER_CONVERSATION = 100


class Bookmark(Base):
    """책갈피 하나. note 는 사람이 붙인 짧은 메모다(없어도 된다)."""

    __tablename__ = 'bookmarks'

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('messages.id', ondelete='CASCADE'), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    note: Mapped[str | None] = mapped_column(String(BOOKMARK_NOTE_MAX_CHARS), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
