# story-server/app/memory/models.py

"""
기억 메모의 테이블(memory_notes). 세션을 지우면(행을 지우면) 함께 지워진다.

chat 의 표에서 사람이 쓴 메모에 필요한 칸만 둔다. 요약이 제안하는 메모(출처, 받아들인 시각)는 그 조각에서 더한다.
메모는 가지와 상관없이 세션에 하나의 목록이다. 앞 가지로 돌아가도 같은 메모가 모델에 간다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 메모 하나의 길이(글자)와 세션 하나의 메모 수의 상한(chat 과 같다).
# 모델에 늘 가므로 입력의 가격 단계(i0)를 넘지 않게 작게 둔다
NOTE_MAX_CHARS = 300
NOTES_PER_CONVERSATION = 20


class MemoryNote(Base):
    """기억 메모 하나. 짧은 글이다."""

    __tablename__ = 'memory_notes'

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
