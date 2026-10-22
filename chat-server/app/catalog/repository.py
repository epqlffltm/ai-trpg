# chat-server/app/catalog/repository.py

"""
모델 목록(ai_models, ai_model_costs)을 읽고 적는 SQL. 커밋하지 않는다.

원가 단가와 날짜판을 바꾼 기록은 적기만 한다. 고치거나 지우는 함수를 두지 않는다(app/catalog/models.py).
"""

from datetime import date

from sqlalchemy import Select, exists, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import AiModel, AiModelCost, AiModelSnapshot


async def get_model(session: AsyncSession, slug: str) -> AiModel | None:
    """그 이름표의 모델. 없으면 None."""
    return await session.get(AiModel, slug)


async def lock_model(session: AsyncSession, slug: str) -> AiModel | None:
    """그 이름표의 모델을 잠그고 읽는다. 트랜잭션이 끝날 때까지 다른 쪽은 기다린다. 없으면 None."""
    return await session.get(AiModel, slug, with_for_update=True, populate_existing=True)


async def list_models(session: AsyncSession) -> list[AiModel]:
    """모든 모델. 회사, 이름표 순서다."""
    query = select(AiModel).order_by(AiModel.vendor, AiModel.slug)
    return list(await session.scalars(query))


async def models_in(session: AsyncSession, slugs: set[str]) -> dict[str, AiModel]:
    """그 이름표들의 모델. 표에 없는 이름표는 들지 않는다."""
    query = select(AiModel).where(AiModel.slug.in_(slugs))
    return {model.slug: model for model in await session.scalars(query)}


async def api_model_taken(session: AsyncSession, provider: str, api_model_id: str) -> bool:
    """같은 창구의 같은 API 모델이 이미 있나."""
    query = select(exists().where(AiModel.provider == provider, AiModel.api_model_id == api_model_id))
    return bool(await session.scalar(query))


async def add_model(session: AsyncSession, model: AiModel) -> None:
    """모델을 적는다."""
    session.add(model)
    await session.flush()


async def add_cost(session: AsyncSession, cost: AiModelCost) -> None:
    """원가 단가를 적는다."""
    session.add(cost)
    await session.flush()


def latest_first(query: Select[tuple[AiModelCost]]) -> Select[tuple[AiModelCost]]:
    """그날에 쓰는 단가가 맨 앞에 오게 늘어놓는다. 늦게 시작한 것, 같은 날이면 나중에 적은 것이 앞이다."""
    return query.order_by(AiModelCost.effective_from.desc(), AiModelCost.id.desc())


async def cost_on(session: AsyncSession, slug: str, day: date) -> AiModelCost | None:
    """그 모델의 그날의 단가. 그날 이전에 시작한 것이 없으면 None."""
    query = select(AiModelCost).where(AiModelCost.model_slug == slug, AiModelCost.effective_from <= day)
    return await session.scalar(latest_first(query).limit(1))


async def costs_on(session: AsyncSession, day: date) -> dict[str, AiModelCost]:
    """모델마다 그날의 단가. 단가가 없는 모델은 들지 않는다. 모델마다 맨 앞의 한 줄만 고른다(DISTINCT ON)."""
    query = (
        select(AiModelCost)
        .where(AiModelCost.effective_from <= day)
        .ext(distinct_on(AiModelCost.model_slug))
        .order_by(AiModelCost.model_slug, AiModelCost.effective_from.desc(), AiModelCost.id.desc())
    )
    return {cost.model_slug: cost for cost in await session.scalars(query)}


async def cost_history(session: AsyncSession, slug: str) -> list[AiModelCost]:
    """그 모델의 단가들. 앞으로 쓸 것까지 모두, 늦게 시작하는 것부터."""
    query = select(AiModelCost).where(AiModelCost.model_slug == slug)
    return list(await session.scalars(latest_first(query)))


async def add_snapshot(session: AsyncSession, snapshot: AiModelSnapshot) -> None:
    """날짜판을 바꾼 일을 적는다."""
    session.add(snapshot)
    await session.flush()


async def snapshot_history(session: AsyncSession, slug: str) -> list[AiModelSnapshot]:
    """그 모델의 날짜판을 바꾼 일들. 나중에 바꾼 것부터."""
    query = select(AiModelSnapshot).where(AiModelSnapshot.model_slug == slug).order_by(AiModelSnapshot.id.desc())
    return list(await session.scalars(query))
