# trpg-server/app/catalog/repository.py

"""
모델 목록(ai_models, ai_model_costs, ai_model_snapshots)을 읽고 적는 SQL. 커밋하지 않는다.

세 서버가 함께 쓰는 쿼리는 catalog_core/repository.py 에 있다. 여기서 이 서버의 표(app/catalog/models.py 의 TABLES)에
묶어 두어, 이 서버의 코드는 표를 넘기지 않고 부른다(repository.get_model(session, slug)).
적는 쿼리(들여오기)는 catalog_core/sync.py 가 직접 부른다. 이 서버만의 칸(회사의 대체 모델)을 고치는 쿼리는 여기 있다.
"""

from functools import partial

from catalog_core import repository as shared
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import TABLES, AiModel

get_model = partial(shared.get_model, TABLES)
list_models = partial(shared.list_models, TABLES)
cost_on = partial(shared.cost_on, TABLES)
costs_on = partial(shared.costs_on, TABLES)
cost_history = partial(shared.cost_history, TABLES)
snapshot_history = partial(shared.snapshot_history, TABLES)


async def clear_fallback(session: AsyncSession, vendor: str) -> None:
    """그 회사의 대체 모델 표시를 지운다. 새로 정하기 전에 먼저 지워야 회사마다 하나라는 제약에 걸리지 않는다."""
    query = update(AiModel).where(AiModel.vendor == vendor, AiModel.vendor_fallback).values(vendor_fallback=False)
    await session.execute(query.execution_options(synchronize_session='fetch'))
