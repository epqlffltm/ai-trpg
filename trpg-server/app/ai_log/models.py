# trpg-server/app/ai_log/models.py

"""
AI 호출의 기록(ai_invocations). 모델을 한 번 부를 때마다 한 줄이다.

게임의 이벤트(table_events)와 따로 둔다. 이벤트는 테이블에서 일어난 일이고 앉은 사람 모두가 읽는다.
이것은 운영과 비용의 기록이다. 플레이어에게 내보내지 않는다.

규칙 셋.
  - 덧붙이기만 한다. 적은 줄은 지우지 않고, 원문(text) 말고는 고치지 않는다. 사용량과 비용의 근거다.
  - 원문은 보관 기간(AI_LOG_TEXT_RETENTION_DAYS, 기본 30일)이 지나면 비운다(app/ai_log/retention.py, #274).
    원문을 볼 수 있는 사람은 DB 에 닿는 운영자뿐이다. API 로 내보내지 않는다.
  - 테이블에 외래 키를 걸지 않는다. 기록은 테이블보다 오래 산다. 테이블이 지워져도 남는다.

생각 글과 보낸 메시지는 적지 않는다(ai_core/calls.py). 보낸 메시지는 지문(HMAC)만 남긴다.
모델 목록의 모델이면 이름표와 원가도 남긴다(ai_core/costs.py). 실제 청구서와 견줄 근거다.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from ai_core.calls import Outcome
from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, Numeric, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import one_of
from app.core.database import Base

# 원문이 남은 줄이라는 조건. 마이그레이션도 같은 글자를 쓴다
TEXT_KEPT = 'text IS NOT NULL'


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
        CheckConstraint(
            'cached_input_tokens >= 0 AND cache_write_tokens >= 0 AND reasoning_tokens >= 0',
            name='token_details_not_negative',
        ),
        CheckConstraint('cost_usd >= 0', name='cost_not_negative'),
        CheckConstraint('input_chars >= 0', name='input_chars_not_negative'),
        # "이 테이블의 호출들"을 시간 순서로 찾는다
        Index('ix_ai_invocations_table_id_created_at', 'table_id', 'created_at'),
        # 보관 기간이 지난 원문을 오래된 것부터 찾는다(app/ai_log/retention.py). 원문이 남은 줄만 색인에 든다.
        # 비운 줄은 빠지므로 정리할 때마다 지금까지의 기록을 모두 훑지 않는다
        Index('ix_ai_invocations_text_kept', 'created_at', postgresql_where=TEXT_KEPT),
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

    # 모델이 쓴 글. 쓰지 않은 글도 남긴다. 받지 못했으면 비어 있다. API 로 내보내지 않는다.
    # 보관 기간이 지나면 비운다(app/ai_log/retention.py)
    text: Mapped[str | None] = mapped_column(Text)

    # 생성 설정. 이 칸이 생기기 전의 줄은 비어 있다
    temperature: Mapped[float | None] = mapped_column(Float)
    max_tokens: Mapped[int | None] = mapped_column(Integer)

    # 프롬프트에 넣은 로어북 항목들(판의 복사본 안의 id). 넣은 것이 없으면 빈 목록이다
    lore_entry_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), server_default='{}')

    # 프롬프트에 넣은 지난 일(같은 테이블의 라운드 번호). 넣은 것이 없으면 빈 목록이다
    memory_rounds: Mapped[list[int]] = mapped_column(ARRAY(Integer), server_default='{}')

    # 프롬프트에 넣은 참고 자료의 줄들(reference_entries 의 id, #482). 넣은 것이 없으면 빈 목록이다.
    # 자료를 다시 넣어 줄이 지워져도 기록은 남는다. 외래 키를 걸지 않는다
    reference_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), server_default='{}')

    # 보낸 메시지의 지문(HMAC-SHA256, 16진수 64자). 서버의 키가 없으면 비어 있다
    input_digest: Mapped[str | None] = mapped_column(String(64))

    # 자세한 토큰 수. 캐시에서 읽은 입력, 캐시에 쓴 입력, 생각에 쓴 출력. 모두 위의 입력·출력 수에 들어 있다.
    # provider 가 알려 주지 않으면, 그리고 이 칸이 생기기 전의 줄은 비어 있다
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)

    # 모델 목록(app/catalog)의 이름표. 목록에 없는 모델(서버 곁의 모델)이면 비어 있다
    model_slug: Mapped[str | None] = mapped_column(String(48))
    # 그날의 단가로 센 원가(USD)와 그 단가의 줄(ai_model_costs.id). 모르면 비어 있다(ai_core/costs.py).
    # 단가의 줄에 외래 키를 걸지 않는다. 기록은 무엇보다 오래 산다(위의 규칙). 단가의 줄도 지우지 않는다
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8))
    cost_id: Mapped[int | None] = mapped_column(Integer)

    # 보낸 메시지의 글자 수의 합. 위의 입력 토큰 수와 나란히 놓아 모델마다 글자당 토큰 수를 잰다.
    # 서술의 입력 예산은 글자 수로 어림한다(app/rounds/budget.py). 그 비율을 이 기록으로 고친다.
    # 이 칸이 생기기 전의 줄은 비어 있다
    input_chars: Mapped[int | None] = mapped_column(Integer)
