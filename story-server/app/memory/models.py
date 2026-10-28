# story-server/app/memory/models.py

"""
기억의 테이블. 기억 메모(memory_notes)와 굴리는 요약(summaries)이다. 세션을 지우면(행을 지우면) 함께 지워진다.

chat 의 표에서 사람이 쓴 메모에 필요한 칸만 둔다. 요약이 제안하는 메모(출처, 받아들인 시각)는 그 조각에서 더한다.
메모는 가지와 상관없이 세션에 하나의 목록이다. 앞 가지로 돌아가도 같은 메모가 모델에 간다.
요약은 파생 데이터다(chat 과 같다). 원본 말은 늘 남고, 요약이 틀리면 원본에서 다시 만든다.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid, func
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


class Summary(Base):
    """
    굴리는 요약 하나. 세션의 첫 말부터 message_id 까지를 요약한 글이다(chat 의 표와 같은 모양).

    세션은 트리라서 첫 말부터 어느 말까지의 길은 하나뿐이다. 그래서 요약을 그 말에 붙이면 어느 가지에서 읽어도 맞다.
    앞 가지로 돌아가면 그 가지에 있는 말의 요약을 쓴다. 부른 모델과 토큰, 원가를 적어 둔다(청구하지 않는다).
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
