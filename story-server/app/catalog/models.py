# story-server/app/catalog/models.py

"""
story 서버의 모델 목록(#591 의 "한 번의 말"). 세션에 쓸 수 있는 언어 모델들과 모델마다의 원가 단가다.

원본은 모델 목록의 파일 하나다(ai_core/model_catalog.toml, #499). 게임 서버와 같은 파일을 이 서버의 표에 들여온다
(scripts.models sync, app/catalog/sync.py). 표는 그 사본에 이 서버만의 스위치를 더한 것이다.
  - enabled: 켜져 있나. 새로 들여온 모델은 꺼져 있다. 원가를 보고 평가 장면을 통과한 뒤에 켠다.
  - allows_adult: 성인 등급의 세션에 쓸 수 있나. 공급자의 약관을 확인한 뒤에 켠다
    (docs/architecture/chat-server.md 의 "성인 콘텐츠"). 한 서비스만 쓰는 속성이라 파일에 두지 않는다.
chat 서버의 표(chat-server/app/catalog/models.py)와 모양이 같다. 회사의 대체 모델은 없고,
모델이 끝나도 몰래 바꾸지 않는다.

표 셋이다.
  - ai_models: 모델 하나에 한 줄.
  - ai_model_costs: 원가 단가(USD, 백만 토큰당). 덧붙이기만 한다.
  - ai_model_snapshots: 날짜판(API 모델 이름)을 바꾼 기록. 덧붙이기만 한다.

판매가(말 한 번에 몇 크레딧)는 여기 없다. 결제 서버의 가격표(story.<이름표>.i0.o0)가 정한다.
모델을 지우지 않는다. 세션와 청구 기록이 그 모델을 가리킨다. 빼려면 끄거나 은퇴일을 적는다(파일).
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from ai_core.catalog_contract import Grade, Provider, ReasoningStyle, TokenLimitField
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

from app.core.database import Base


def one_of(column: str, values: type[enum.StrEnum]) -> str:
    """칸의 값이 그 목록 안에 있다는 CHECK 의 글자."""
    allowed = ', '.join(f"'{value}'" for value in values)
    return f'{column} IN ({allowed})'


# 단가 칸의 자릿수. 백만 토큰당 USD 를 소수 여섯째 자리까지 적는다($0.075 같은 값이 있다)
PRICE_TYPE = Numeric(12, 6)


class AiModel(Base):
    """세션에 쓸 수 있는 모델 하나."""

    __tablename__ = 'ai_models'
    __table_args__ = (
        CheckConstraint(one_of('provider', Provider), name='provider_allowed'),
        CheckConstraint(one_of('grade', Grade), name='grade_allowed'),
        CheckConstraint(
            f'token_limit_field IS NULL OR {one_of("token_limit_field", TokenLimitField)}', name='token_field_allowed'
        ),
        CheckConstraint(
            f'reasoning_style IS NULL OR {one_of("reasoning_style", ReasoningStyle)}', name='reasoning_style_allowed'
        ),
        # 같은 창구의 같은 모델을 두 이름표로 넣지 않는다. 목록에 같은 모델이 둘 보인다
        UniqueConstraint('provider', 'api_model_id', name='uq_ai_models_api_model'),
    )

    # 이름표. 결제 서버의 가격 코드(story.<이름표>.i0.o0)와 세션, 기록이 이것으로 모델을 가리킨다
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
    # 생각을 켜고 끄는 방식(ReasoningStyle). 방식이 모델마다 다른 창구만 적는다(ai_core/catalog_contract.py)
    reasoning_style: Mapped[str | None] = mapped_column(String(20))

    # 켜져 있나. 새로 들여온 모델은 꺼져 있다. 파일에 없는 이 서버의 스위치다
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))
    # 이 날부터 쓰지 않는다. 공급자가 모델을 내리는 날이다(파일의 retires_on). 없으면 정해지지 않았다
    retires_on: Mapped[date | None] = mapped_column(Date)
    # 성인 등급의 세션에 쓸 수 있나. 이 서버만의 스위치다(파일에 없다). 공급자의 약관을 확인한 뒤에 켠다
    allows_adult: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))

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


class AiModelSnapshot(Base):
    """날짜판을 바꾼 일 하나. 앞의 이름과 새 이름. 덧붙이기만 한다."""

    __tablename__ = 'ai_model_snapshots'
    __table_args__ = (
        CheckConstraint('previous_api_model_id <> api_model_id', name='snapshot_changes'),
        # "이 모델의 날짜판이 어떻게 바뀌었나"를 바꾼 순서대로 찾는다
        Index('ix_ai_model_snapshots_model_slug_id', 'model_slug', 'id'),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    model_slug: Mapped[str] = mapped_column(ForeignKey('ai_models.slug', ondelete='RESTRICT'))
    previous_api_model_id: Mapped[str] = mapped_column(String(200))
    api_model_id: Mapped[str] = mapped_column(String(200))
    # 덧붙일 말(공급자의 공지, 바꾼 까닭 …)
    note: Mapped[str | None] = mapped_column(String(200))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
