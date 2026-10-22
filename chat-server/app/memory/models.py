# chat-server/app/memory/models.py

"""
기억 메모의 테이블. 대화를 지우면(행을 지우면) 함께 지워진다.

출처(source)는 사용자가 쓴 것(user)과 요약이 제안한 것(summary)이다. 요약의 제안은 굴리는 요약의 PR 에서 쓴다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.conversations.models import one_of
from app.core.database import Base

# 메모 하나의 길이(글자)와 대화 하나의 메모 수의 상한. 모델에 늘 가므로 입력의 가격 단계(i0)를 넘지 않게 작게 둔다
NOTE_MAX_CHARS = 300
NOTES_PER_CONVERSATION = 20


class NoteSource(enum.StrEnum):
    """메모를 누가 썼는가."""

    USER = 'user'
    SUMMARY = 'summary'


class MemoryNote(Base):
    """기억 메모 하나. 짧은 글이다."""

    __tablename__ = 'memory_notes'
    __table_args__ = (CheckConstraint(one_of('source', NoteSource), name='source_allowed'),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default=NoteSource.USER)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
