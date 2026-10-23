# chat-server/app/reports/models.py

"""
대화 속 캐릭터의 답의 신고(message_reports, #678).

사적 1:1 대화는 운영자가 읽지 않는다(docs/architecture/chat-server.md 의 "운영과 신고"). 그래서 신고하는 순간
신고한 답과 그 앞의 몇 마디(CONTEXT_MESSAGES)를 신고에 굳혀 둔다. 운영자는 대화 전체가 아니라 이것만 본다.
그 뒤에 말을 고치거나 가지를 바꿔도 신고한 때의 글이 남는다.

  - 신고할 수 있는 것은 자기 대화의 캐릭터의 답이다(사람의 말은 신고하지 않는다). 같은 답은 한 번만이다
  - 운영자가 처리하면 처리한 시각, 처리한 사람, 결과를 함께 적는다. 셋은 함께 있거나 함께 없다
  - 대화를 지우면(행. 탈퇴할 때) 신고도 지워진다. 신고에 든 것은 신고한 사람의 대화이기 때문이다.
    대화 지우기(지운 것으로 적기)로는 지워지지 않는다
  - 사유는 asset 의 캐릭터 신고와 같다(spam, abuse, sexual, minor, illegal, other)
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 설명의 가장 긴 길이(asset 의 신고와 같다)
DESCRIPTION_MAX_LENGTH = 500
# 신고에 굳히는 앞의 말의 수(신고한 답은 빼고)
CONTEXT_MESSAGES = 6


class ReportReason(enum.StrEnum):
    """신고의 사유. asset 의 캐릭터 신고와 같다. minor 는 운영자의 목록에서 가장 먼저 보인다."""

    SPAM = 'spam'
    ABUSE = 'abuse'
    SEXUAL = 'sexual'
    MINOR = 'minor'
    ILLEGAL = 'illegal'
    OTHER = 'other'


class ReportOutcome(enum.StrEnum):
    """처리의 결과. 받아들였다, 받아들이지 않았다. 캐릭터를 숨기는 것은 asset 의 운영자 API 다."""

    ACTIONED = 'actioned'
    DISMISSED = 'dismissed'


def one_of(column: str, values: type[enum.StrEnum]) -> str:
    """칸의 값이 열거의 값 가운데 하나라는 CHECK 의 식."""
    allowed = ', '.join(f"'{value}'" for value in values)
    return f'{column} IN ({allowed})'


class MessageReport(Base):
    """신고 하나와 그때 굳힌 글."""

    __tablename__ = 'message_reports'
    __table_args__ = (
        CheckConstraint(one_of('reason', ReportReason), name='reason_allowed'),
        CheckConstraint(f'outcome IS NULL OR {one_of("outcome", ReportOutcome)}', name='outcome_allowed'),
        CheckConstraint(
            '(handled_at IS NULL) = (handled_by IS NULL) AND (handled_at IS NULL) = (outcome IS NULL)',
            name='handled_together',
        ),
        UniqueConstraint('reporter_id', 'message_id', name='uq_message_reports_reporter_message'),
        Index('ix_message_reports_open', 'created_at', postgresql_where='handled_at IS NULL'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reporter_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('messages.id', ondelete='CASCADE'))
    # 어느 캐릭터의 어느 판이었나(asset 의 캐릭터 id 와 판 번호, 그때의 이름). 운영자가 asset 에서 숨길 때 쓴다
    character_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    character_version: Mapped[int] = mapped_column(Integer)
    character_name: Mapped[str] = mapped_column(Text)
    # 그 답을 쓴 대화의 모델(이름표). 모델의 문제인지 캐릭터의 문제인지 가른다
    model_slug: Mapped[str | None] = mapped_column(String(100), default=None)
    reason: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text, default='', server_default='')
    # 신고한 답의 글과 그 앞의 말들 [{"role", "content"}](오래된 것부터). 신고한 때의 것이다
    content: Mapped[str] = mapped_column(Text)
    context: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    handled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    outcome: Mapped[str | None] = mapped_column(String(20), default=None)
