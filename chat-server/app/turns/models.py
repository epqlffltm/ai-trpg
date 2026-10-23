# chat-server/app/turns/models.py

"""
호출과 청구의 기록(generations). 모델을 한 번 부를 때마다 한 줄이다
(docs/architecture/chat-server.md 의 "데이터의 모양").

한 줄이 두 가지를 적는다.
  - 청구: 결제 서버의 홀드 하나(이름표 reference)와 그 상태(billing_status). 호출이 하나면 청구도 하나다.
  - 호출: 어느 모델로, 무엇에 답했고(parent_id), 무엇이 저장됐고(message_id), 어떻게 끝났고(outcome), 토큰과 원가.

청구의 상태는 한 방향으로만 간다.

    pending ─ 홀드를 건다 ─▶ held ─ 답이 끝났다 ─▶ capture_due ─▶ captured
       │                      │                      (확정을 못 했으면 정리 작업이 마저 한다)
       │                      └─ 글자 없이 실패 ───▶ release_due ─▶ released
       └─ 걸리지 않았다(모자람, 팔지 않음, 결제 서버가 죽음) ─▶ declined
    결제 서버가 받아들이지 않으면(다시 불러도 같다) failed 다. 사람이 본다.

pending 이나 held 인 채로 오래 남은 줄은 서버가 말 한 번의 도중에 꺼진 것이다. 정리 작업이 돌려준다(release_due).
대화의 행을 지우면(탈퇴) 함께 지워진다. 사람에게 보여 주지 않는 운영의 기록이다.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BillingStatus(enum.StrEnum):
    """청구가 어디까지 왔나."""

    PENDING = 'pending'
    HELD = 'held'
    DECLINED = 'declined'
    CAPTURE_DUE = 'capture_due'
    RELEASE_DUE = 'release_due'
    CAPTURED = 'captured'
    RELEASED = 'released'
    FAILED = 'failed'


class Outcome(enum.StrEnum):
    """호출이 어떻게 끝났나. complete 와 partial 은 말이 저장됐고 청구한다. failed 는 글자가 하나도 없었다."""

    COMPLETE = 'complete'
    PARTIAL = 'partial'
    FAILED = 'failed'


# 결제 서버에 맡길 차례가 된 상태
DUE_STATUSES = frozenset({BillingStatus.CAPTURE_DUE, BillingStatus.RELEASE_DUE})
# 말 한 번의 도중인 상태. 오래 남으면 서버가 꺼진 것이다
OPEN_STATUSES = frozenset({BillingStatus.PENDING, BillingStatus.HELD})


def one_of(column: str, values: type[enum.StrEnum]) -> str:
    """칸의 값이 그 목록 안에 있다는 CHECK 의 글자."""
    allowed = ', '.join(f"'{value}'" for value in values)
    return f'{column} IN ({allowed})'


class Generation(Base):
    """모델을 한 번 부른 것과 그 청구."""

    __tablename__ = 'generations'
    __table_args__ = (
        CheckConstraint(one_of('billing_status', BillingStatus), name='billing_status_allowed'),
        CheckConstraint(f'outcome IS NULL OR {one_of("outcome", Outcome)}', name='outcome_allowed'),
        # 정리 작업이 맡길 차례가 된 청구를 찾는다
        Index('ix_generations_billing_status_next_settle_at', 'billing_status', 'next_settle_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 대화와 말을 가리키는 칸은 그것이 지워지면 비운다(SET NULL). 기록은 남는다.
    # 대화가 지워지는 것은 탈퇴뿐이다(app/withdrawal/, #670). 남은 기록은 결제 서버의 원장과 맞추고 원가를 셀 때 쓴다
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('conversations.id', ondelete='SET NULL'), index=True
    )
    # 크레딧을 내는 사람(인증 서버의 public_id)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 무엇에 답했나(사람의 말). 저장된 답(message_id)의 부모다
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('messages.id', ondelete='SET NULL'))
    # 저장된 답. 글자 없이 실패했거나 아직 끝나지 않았으면 비어 있다
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('messages.id', ondelete='SET NULL'), default=None)
    model_slug: Mapped[str] = mapped_column(ForeignKey('ai_models.slug', ondelete='RESTRICT'))

    # 결제 서버의 홀드의 이름표(chat:gen:<id>)와 가격표 이름(chat.<이름표>.i0.o0)
    reference: Mapped[str] = mapped_column(String(80), unique=True)
    price_code: Mapped[str] = mapped_column(String(120))
    billing_status: Mapped[str] = mapped_column(String(20), default=BillingStatus.PENDING)
    # 결제 서버에 맡기지 못한 횟수와, 다음에 맡길 때. 맡기지 못할수록 늦게 다시 부른다(app/turns/settler.py)
    settle_attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_settle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    outcome: Mapped[str | None] = mapped_column(String(20), default=None)
    # 왜 그렇게 끝났나(timeout, status_429, credit_short …). 공급자와 결제 서버의 답의 본문은 싣지 않는다
    error_code: Mapped[str | None] = mapped_column(String(60), default=None)
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    # 모델 목록의 그날의 단가로 센 원가(USD). 단가가 없거나 토큰 수를 모르면 비어 있다
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
