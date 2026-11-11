# shared/catalog-core/src/catalog_core/repository.py

"""
모델 목록(ai_models, ai_model_costs, ai_model_snapshots)을 읽고 적는 SQL. 커밋하지 않는다.
tables 는 서버의 표 셋이다(catalog_core/tables.py). 맨 앞에 받는다. 서버가 제 표를 한 번 묶어 두고
(서버의 app/catalog/repository.py 의 partial) 표 없이 부르게 하려는 것이다.

원가 단가와 날짜판을 바꾼 기록은 적기만 한다. 고치거나 지우는 함수를 두지 않는다.
서버만의 칸을 다루는 쿼리(trpg 의 회사의 대체 모델)는 서버에 둔다.
"""

from datetime import date
from typing import Any

from sqlalchemy import Select, exists, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_core.tables import CatalogTables


async def get_model(tables: CatalogTables, session: AsyncSession, slug: str) -> Any | None:
    """그 이름표의 모델. 없으면 None."""
    return await session.get(tables.model, slug)


async def lock_model(tables: CatalogTables, session: AsyncSession, slug: str) -> Any | None:
    """그 이름표의 모델을 잠그고 읽는다. 트랜잭션이 끝날 때까지 다른 쪽은 기다린다. 없으면 None."""
    return await session.get(tables.model, slug, with_for_update=True, populate_existing=True)


async def list_models(tables: CatalogTables, session: AsyncSession) -> list[Any]:
    """모든 모델. 회사, 이름표 순서다."""
    query = select(tables.model).order_by(tables.model.vendor, tables.model.slug)
    return list(await session.scalars(query))


async def models_in(tables: CatalogTables, session: AsyncSession, slugs: set[str]) -> dict[str, Any]:
    """그 이름표들의 모델. 표에 없는 이름표는 들지 않는다."""
    query = select(tables.model).where(tables.model.slug.in_(slugs))
    return {model.slug: model for model in await session.scalars(query)}


async def api_model_taken(tables: CatalogTables, session: AsyncSession, provider: str, api_model_id: str) -> bool:
    """같은 창구의 같은 API 모델이 이미 있나."""
    model = tables.model
    query = select(exists().where(model.provider == provider, model.api_model_id == api_model_id))
    return bool(await session.scalar(query))


async def add(session: AsyncSession, row: Any) -> None:
    """모델, 원가 단가, 날짜판을 바꾼 일 가운데 하나를 적는다."""
    session.add(row)
    await session.flush()


def latest_first(tables: CatalogTables, query: Select) -> Select:
    """그날에 쓰는 단가가 맨 앞에 오게 늘어놓는다. 늦게 시작한 것, 같은 날이면 나중에 적은 것이 앞이다."""
    return query.order_by(tables.cost.effective_from.desc(), tables.cost.id.desc())


async def cost_on(tables: CatalogTables, session: AsyncSession, slug: str, day: date) -> Any | None:
    """그 모델의 그날의 단가. 그날 이전에 시작한 것이 없으면 None."""
    cost = tables.cost
    query = select(cost).where(cost.model_slug == slug, cost.effective_from <= day)
    return await session.scalar(latest_first(tables, query).limit(1))


async def costs_on(tables: CatalogTables, session: AsyncSession, day: date) -> dict[str, Any]:
    """모델마다 그날의 단가. 단가가 없는 모델은 들지 않는다. 모델마다 맨 앞의 한 줄만 고른다(DISTINCT ON)."""
    cost = tables.cost
    query = (
        select(cost)
        .where(cost.effective_from <= day)
        .ext(distinct_on(cost.model_slug))
        .order_by(cost.model_slug, cost.effective_from.desc(), cost.id.desc())
    )
    return {row.model_slug: row for row in await session.scalars(query)}


async def cost_history(tables: CatalogTables, session: AsyncSession, slug: str) -> list[Any]:
    """그 모델의 단가들. 앞으로 쓸 것까지 모두, 늦게 시작하는 것부터."""
    query = select(tables.cost).where(tables.cost.model_slug == slug)
    return list(await session.scalars(latest_first(tables, query)))


async def snapshot_history(tables: CatalogTables, session: AsyncSession, slug: str) -> list[Any]:
    """그 모델의 날짜판을 바꾼 일들. 나중에 바꾼 것부터."""
    snapshot = tables.snapshot
    query = select(snapshot).where(snapshot.model_slug == slug).order_by(snapshot.id.desc())
    return list(await session.scalars(query))
