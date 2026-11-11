# shared/catalog-core/tests/tables.py

"""
테스트의 모델 목록 표 셋. 서버의 표(chat-server/app/catalog/models.py 등)와 칸의 이름이 같다.

서버만의 칸 하나(vendor_fallback)를 두어, 회사가 바뀔 때 서버의 자리(on_vendor_change)가 불리는지 본다.
제약과 색인은 두지 않는다. 그것은 서버의 마이그레이션과 테스트(실제 PostgreSQL)가 본다.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from catalog_core.tables import CatalogTables

PRICE_TYPE = Numeric(12, 6)


class Base(DeclarativeBase):
    pass


class AiModel(Base):
    __tablename__ = 'ai_models'

    slug: Mapped[str] = mapped_column(String(48), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    api_model_id: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(80))
    vendor: Mapped[str] = mapped_column(String(30))
    grade: Mapped[str] = mapped_column(String(10))
    supports_reasoning: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_temperature: Mapped[bool] = mapped_column(Boolean, default=True)
    token_limit_field: Mapped[str | None] = mapped_column(String(30))
    reasoning_style: Mapped[str | None] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    retires_on: Mapped[date | None] = mapped_column(Date)
    # 서버만의 칸(trpg 의 회사의 대체 모델과 같은 모양)
    vendor_fallback: Mapped[bool] = mapped_column(Boolean, default=False)


class AiModelCost(Base):
    __tablename__ = 'ai_model_costs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_slug: Mapped[str] = mapped_column(ForeignKey('ai_models.slug'))
    input_per_mtok: Mapped[Decimal] = mapped_column(PRICE_TYPE)
    cached_input_per_mtok: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    cache_write_per_mtok: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    output_per_mtok: Mapped[Decimal] = mapped_column(PRICE_TYPE)
    effective_from: Mapped[date] = mapped_column(Date)
    checked_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(200))


class AiModelSnapshot(Base):
    __tablename__ = 'ai_model_snapshots'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_slug: Mapped[str] = mapped_column(ForeignKey('ai_models.slug'))
    previous_api_model_id: Mapped[str] = mapped_column(String(200))
    api_model_id: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(String(200))


def drop_fallback(model: Any) -> None:
    """회사가 바뀌면 대체 모델 표시를 내린다(trpg 의 것과 같다)."""
    model.vendor_fallback = False


# chat 과 story 처럼 서버만의 칸을 회사와 묶지 않은 꾸러미
PLAIN = CatalogTables(AiModel, AiModelCost, AiModelSnapshot)
# trpg 처럼 회사가 바뀌면 서버만의 칸을 고치는 꾸러미
WITH_FALLBACK = CatalogTables(AiModel, AiModelCost, AiModelSnapshot, on_vendor_change=drop_fallback)
