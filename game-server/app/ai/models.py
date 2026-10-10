# game-server/app/ai/models.py

"""
AI 호출의 기록(ai_invocations). 모델을 한 번 부를 때마다 한 줄이다.

게임의 이벤트(table_events)와 따로 둔다. 이벤트는 테이블에서 일어난 일이고 앉은 사람 모두가 읽는다.
이것은 운영과 비용의 기록이다. 플레이어에게 내보내지 않는다.

규칙 둘.
  - 덧붙이기만 한다. 적은 줄은 고치지 않고 지우지 않는다. 사용량과 비용의 근거다.
  - 테이블에 외래 키를 걸지 않는다. 기록은 테이블보다 오래 산다. 테이블이 지워져도 남는다.

생각 글과 보낸 메시지는 적지 않는다(app/ai/calls.py). 보낸 메시지는 지문(HMAC)만 남긴다.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.calls import Outcome
from app.assets.models import one_of
from app.core.database import Base


class AiInvocation(Base):
    """AI 호출 한 번."""

    __tablename__ = 'ai_invocations'
    __table_args__ = (
        CheckConstraint(one_of('outcome', Outcome), name='outcome_allowed'),
        # 잘 끝난 호출에만 이유가 없다. 쓰지 않았거나 받지 못했으면 이유가 있다
        CheckConstraint("(outcome = 'ok') = (error IS NULL)", name='error_unless_ok'),
        # 받지 못한 호출에는 글이 없다
        CheckConstraint("outcome <> 'failed' OR text IS NULL", name='no_text_when_failed'),
        CheckConstraint('latency_ms >= 0', name='latency_not_negative'),
        CheckConstraint('input_tokens >= 0 AND output_tokens >= 0', name='tokens_not_negative'),
        CheckConstraint('max_tokens > 0', name='max_tokens_positive'),
        # "이 테이블의 호출들"을 시간 순서로 찾는다
        Index('ix_ai_invocations_table_id_created_at', 'table_id', 'created_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 무엇을 위해 불렀나(narration)
    purpose: Mapped[str] = mapped_column(String(40))
    # 어느 테이블의 몇 번째 라운드에서, 그때 방장이 누구일 때. 테이블 밖의 호출이면 비어 있다
    table_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    round_number: Mapped[int | None] = mapped_column(Integer)
    host_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    # 어떤 조건으로 불렀나
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(40))
    reasoning: Mapped[str] = mapped_column(String(20))
    # 서술의 문체. 서술이 아닌 호출이면 비어 있다
    narration_style: Mapped[str | None] = mapped_column(String(20))

    # 어떻게 끝났나. 잘 끝나지 않았으면 그 이유(cut_off, timeout …)
    outcome: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(String(40))

    # 걸린 시간과, provider 가 알려 준 토큰 수와 멈춘 이유. 모르면 비어 있다
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    finish_reason: Mapped[str | None] = mapped_column(String(40))

    # 모델이 쓴 글. 쓰지 않은 글도 남긴다. 받지 못했으면 비어 있다. API 로 내보내지 않는다
    text: Mapped[str | None] = mapped_column(Text)

    # 생성 설정. 이 칸이 생기기 전의 줄은 비어 있다
    temperature: Mapped[float | None] = mapped_column(Float)
    max_tokens: Mapped[int | None] = mapped_column(Integer)

    # 프롬프트에 넣은 로어북 항목들(판의 복사본 안의 id). 넣은 것이 없으면 빈 목록이다
    lore_entry_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), server_default='{}')

    # 프롬프트에 넣은 지난 일(같은 테이블의 라운드 번호). 넣은 것이 없으면 빈 목록이다
    memory_rounds: Mapped[list[int]] = mapped_column(ARRAY(Integer), server_default='{}')

    # 보낸 메시지의 지문(HMAC-SHA256, 16진수 64자). 서버의 키가 없으면 비어 있다
    input_digest: Mapped[str | None] = mapped_column(String(64))
