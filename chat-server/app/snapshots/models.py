# chat-server/app/snapshots/models.py

"""
장면 그림 한 장의 기록과 그 청구(snapshots, #983).

말 한 번의 기록(app/turns/models.py 의 generations)과 같은 청구의 상태를 쓴다(BillingStatus, 한 방향으로만 간다).
따로 두는 까닭: 그림 모델은 글 모델의 목록(ai_models)에 없고, 그림 한 장은 말을 저장하지 않는다(그림의 id 를 적는다).

  - 한 대화에 그리는 중인 것(outcome 이 비어 있다)은 하나다(부분 유일 색인). 두 요청이 함께 와도 하나만 들어간다
  - 그림은 asset 서버의 그림이다(image_id). 그 사람만 본다. 대화를 지우면 asset 에 지우라고 한다
  - 대화나 말의 행이 지워지면(탈퇴) 그 칸만 비운다. 기록은 결제 서버의 원장과 맞추려고 남는다
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.turns.models import BillingStatus, one_of


class SnapshotOutcome(enum.StrEnum):
    """한 장이 어떻게 끝났나. 비어 있으면 그리는 중이다."""

    READY = 'ready'
    FAILED = 'failed'


class Snapshot(Base):
    """장면 그림 한 장."""

    __tablename__ = 'snapshots'
    __table_args__ = (
        CheckConstraint(one_of('billing_status', BillingStatus), name='billing_status_allowed'),
        CheckConstraint(f'outcome IS NULL OR {one_of("outcome", SnapshotOutcome)}', name='outcome_allowed'),
        # 한 대화에 그리는 중인 것은 하나다
        Index(
            'uq_snapshots_one_drawing',
            'conversation_id',
            unique=True,
            postgresql_where=text('outcome IS NULL'),
        ),
        # 대화의 그림들을 말의 차례로 찾는다
        Index('ix_snapshots_conversation_created', 'conversation_id', 'created_at'),
        # 정리 작업이 맡길 차례가 된 청구를 찾는다
        Index('ix_snapshots_billing_status_next_settle_at', 'billing_status', 'next_settle_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('conversations.id', ondelete='SET NULL'))
    # 그린 장면인 캐릭터의 답
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('messages.id', ondelete='SET NULL'))
    # 크레딧을 내는 사람(인증 서버의 public_id). 그림의 주인이기도 하다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 그림 모델의 이름(gemini-nano-banana-2.1 같은 것)
    model: Mapped[str] = mapped_column(String(80))

    # 결제 서버의 홀드의 이름표(chat:img:<id>)와 가격표 이름(chat.image.<이름표>)
    reference: Mapped[str] = mapped_column(String(80), unique=True)
    price_code: Mapped[str] = mapped_column(String(120))
    billing_status: Mapped[str] = mapped_column(String(20), default=BillingStatus.PENDING)
    settle_attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_settle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    outcome: Mapped[str | None] = mapped_column(String(20), default=None)
    # 왜 실패했나(refused, no_image, timeout, credit_short …). 공급자와 결제 서버의 답의 본문은 싣지 않는다
    error_code: Mapped[str | None] = mapped_column(String(60), default=None)
    # asset 서버의 그림 id. 다 그리고 맡긴 뒤에 채운다
    image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
