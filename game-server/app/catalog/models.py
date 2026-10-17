# game-server/app/catalog/models.py

"""
모델 목록. 서술에 쓸 수 있는 언어 모델들과, 모델마다의 원가 단가다.

표 둘이다.
  - ai_models: 모델 하나에 한 줄. 어느 창구(provider)로 부르고, API 에 어떤 이름으로 보내고, 어떻게 보이고, 켜져 있는가.
  - ai_model_costs: 모델의 원가 단가(USD, 백만 토큰당). 덧붙이기만 한다. 고치지도 지우지도 않는다.
    공급자가 가격을 바꾸면 새 줄을 적는다. 그래야 "그때 원가가 얼마였나"를 나중에 볼 수 있다.

판매가(1인 1라운드에 몇 크레딧)는 여기 없다. 결제 서버의 가격표(price_versions)가 정한다.
여기는 공급자에게 내는 값이다. 판매가를 정할 때와 실제 사용량의 원가를 잴 때 쓴다.

규칙 몇 가지.
  - 모델을 지우지 않는다. 지난 라운드와 청구 기록이 그 모델을 가리킨다.
    빼려면 끄거나(enabled) 은퇴일(retires_on)을 적는다.
  - 이름표(slug), 창구, API 모델 이름은 만든 뒤에 바꾸지 않는다. API 모델 이름이 바뀌면 다른 모델이다.
    같은 이름표가 다른 모델을 가리키면 서술의 목소리가 말없이 바뀐다. 새 줄로 넣는다.
  - API 모델 이름에는 날짜가 붙은 이름(스냅숏)을 적는다. 별칭(gpt-x-latest 같은)은 공급자가 말없이 다른 모델로 돌린다.
  - 새로 넣은 모델은 꺼진 채로 시작한다. 원가를 적고, 평가 장면을 통과한 뒤에 켠다.

창구(provider)와 분류(grade)는 코드가 아는 값만 받는다.
새 창구는 그것을 부르는 코드가 있어야 하므로 마이그레이션과 함께 늘린다.
회사(vendor)는 보이는 데만 쓰는 이름이라 모양만 본다(app/catalog/schemas.py).

외부에 내보내지 않는다. 지금은 관리 명령(scripts/models.py)으로만 다룬다.
나중에 관리 서버가 같은 함수들(app/catalog/service.py)을 부른다.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import one_of
from app.core.database import Base

# 단가 칸의 자릿수. 백만 토큰당 USD 를 소수 여섯째 자리까지 적는다($0.075 같은 값이 있다)
PRICE_TYPE = Numeric(12, 6)


class Provider(enum.StrEnum):
    """모델을 부르는 창구. 창구마다 부르는 코드가 따로 있다."""

    # OpenAI 의 API
    OPENAI = 'openai'
    # Anthropic 의 API(Claude)
    ANTHROPIC = 'anthropic'
    # Google 의 Gemini API
    GEMINI = 'gemini'
    # 서버 곁에서 도는 모델(Ollama, LM Studio). 설정의 LLM_BASE_URL 로 부른다
    LOCAL = 'local'


class Grade(enum.StrEnum):
    """보이는 분류. 목록을 묶어 보이는 데만 쓴다. 값은 모델마다 따로 정한다."""

    # 아주 싸거나 행사로 풀 모델. 서버 곁의 모델로 한다
    BASIC = 'basic'
    STANDARD = 'standard'
    # 비싼 모델(Opus, Fable, Astra, Argon)
    PREMIUM = 'premium'


class TokenLimitField(enum.StrEnum):
    """
    OpenAI 모양의 API 에서 출력 상한을 담는 칸의 이름. 모델마다 받는 칸이 다르다.

    서버 곁의 모델과 옛 모델은 max_tokens 를, OpenAI 의 생각하는 모델은 max_completion_tokens 만 받는다.
    Claude 와 Gemini 의 API 는 칸이 하나로 정해져 있어 적지 않는다.
    """

    MAX_TOKENS = 'max_tokens'
    MAX_COMPLETION_TOKENS = 'max_completion_tokens'


class AiModel(Base):
    """서술에 쓸 수 있는 모델 하나."""

    __tablename__ = 'ai_models'
    __table_args__ = (
        CheckConstraint(one_of('provider', Provider), name='provider_allowed'),
        CheckConstraint(one_of('grade', Grade), name='grade_allowed'),
        CheckConstraint(
            f'token_limit_field IS NULL OR {one_of("token_limit_field", TokenLimitField)}', name='token_field_allowed'
        ),
        # 같은 창구의 같은 모델을 두 이름표로 넣지 않는다. 목록에 같은 모델이 둘 보인다
        UniqueConstraint('provider', 'api_model_id', name='uq_ai_models_api_model'),
    )

    # 이름표. 결제 서버의 가격 코드(narration.<이름표>.i0.o0)와 기록이 이것으로 모델을 가리킨다
    slug: Mapped[str] = mapped_column(String(48), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    # API 에 보내는 모델 이름. 날짜가 붙은 이름이다
    api_model_id: Mapped[str] = mapped_column(String(200))
    # 보이는 이름과 회사, 분류
    display_name: Mapped[str] = mapped_column(String(80))
    vendor: Mapped[str] = mapped_column(String(30))
    grade: Mapped[str] = mapped_column(String(10))

    # 모델이 받는 것. 생각의 깊이를 고를 수 있나, 온도를 받나, 출력 상한을 어느 칸으로 받나
    supports_reasoning: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))
    supports_temperature: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text('true'))
    token_limit_field: Mapped[str | None] = mapped_column(String(30))

    # 켜져 있나. 새로 넣은 모델은 꺼져 있다
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))
    # 이 날부터 쓰지 않는다. 공급자가 모델을 내리는 날이다. 없으면 정해지지 않았다
    retires_on: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AiModelCost(Base):
    """모델의 원가 단가 하나. effective_from 부터 쓴다. 덧붙이기만 한다."""

    __tablename__ = 'ai_model_costs'
    __table_args__ = (
        CheckConstraint(
            'input_per_mtok >= 0 AND output_per_mtok >= 0'
            ' AND (cached_input_per_mtok IS NULL OR cached_input_per_mtok >= 0)'
            ' AND (cache_write_per_mtok IS NULL OR cache_write_per_mtok >= 0)',
            name='prices_not_negative',
        ),
        # "이 모델의 그날의 단가"를 찾는다. 그날 이전에 시작한 것 중 가장 늦은 것, 같은 날이면 나중에 적은 것이다
        Index('ix_ai_model_costs_model_slug_effective_from', 'model_slug', 'effective_from', 'id'),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    model_slug: Mapped[str] = mapped_column(ForeignKey('ai_models.slug', ondelete='RESTRICT'))

    # USD, 백만 토큰당. 캐시 읽기와 캐시 쓰기는 따로 값을 매기는 공급자만 적는다
    input_per_mtok: Mapped[Decimal] = mapped_column(PRICE_TYPE)
    cached_input_per_mtok: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    cache_write_per_mtok: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    output_per_mtok: Mapped[Decimal] = mapped_column(PRICE_TYPE)

    # 이 날부터의 값이다. 공급자가 미리 알린 값 바꿈(행사가 끝나는 날)도 미리 적어 둔다
    effective_from: Mapped[date] = mapped_column(Date)
    # 공식 가격표에서 확인한 날
    checked_on: Mapped[date] = mapped_column(Date)
    # 덧붙일 말(행사가, 긴 입력은 값이 다름 …)
    note: Mapped[str | None] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
