# chat-server/app/memory/models.py

"""
기억의 테이블. 기억 메모(memory_notes)와 굴리는 요약(summaries)이다. 대화를 지우면(행을 지우면) 함께 지워진다.

메모의 출처(source)는 사용자가 쓴 것(user)과 요약이 제안한 것(summary)이다.
요약은 파생 데이터다. 원본 말은 늘 남고, 요약이 틀리면 원본에서 다시 만든다.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid, func
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


class Summary(Base):
    """
    굴리는 요약 하나. 대화의 첫 말부터 message_id(covered_up_to)까지를 요약한 글이다.

    대화는 트리라서 첫 말부터 어느 말까지의 길은 하나뿐이다. 그래서 요약을 그 말에 붙이면 어느 가지에서 읽어도 맞다.
    앞 가지로 돌아가면 그 가지에 있는 말의 요약을 쓴다. 버리고 다시 만들 일이 없다.
    부른 모델과 토큰, 원가를 적어 둔다. 원가는 서비스가 낸다(청구하지 않는다).
    """

    __tablename__ = 'summaries'

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('messages.id', ondelete='CASCADE'), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    text: Mapped[str] = mapped_column(Text)
    model_slug: Mapped[str] = mapped_column(String(48))
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
