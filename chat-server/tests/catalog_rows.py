# chat-server/tests/catalog_rows.py

"""
테스트가 모델 목록의 표에 모델과 원가를 넣는 도우미. 게임 서버의 것(trpg-server/tests/catalog_rows.py)과 같다.

  - put_models: 모델 목록의 파일을 들여오는 길(app/catalog/sync.py)로 넣거나 고친다. 새 모델은 꺼진 채다.
    운영에서 모델이 표에 들어가는 길이 이것 하나라 테스트도 같은 길로 넣는다.
  - add_cost: 원가 한 줄을 바로 적는다. 파일의 단가를 들여온 것과 같다(단가만 더해 보는 테스트가 쓴다).
  - retire: 은퇴일을 바로 적는다. 파일의 retires_on 을 바꿔 들여온 것과 같다.
"""

from datetime import date

from ai_core.catalog_file import FORMAT, CostEntry, ModelCatalog, ModelEntry
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import AiModel, AiModelCost
from app.catalog.sync import SyncReport, sync_catalog


def catalog_of(*entries: ModelEntry) -> ModelCatalog:
    """모델들로 된 파일."""
    return ModelCatalog(format=FORMAT, models=entries)


async def put_models(session: AsyncSession, *entries: ModelEntry) -> SyncReport:
    """모델들을 들여온다. 파일에 없는 표의 모델은 그대로 둔다."""
    return await sync_catalog(session, catalog_of(*entries))


async def add_cost(session: AsyncSession, slug: str, cost: CostEntry) -> AiModelCost:
    """원가 한 줄을 적는다."""
    row = AiModelCost(model_slug=slug, **cost.model_dump())
    session.add(row)
    await session.commit()
    return row


async def retire(session: AsyncSession, slug: str, on: date | None) -> None:
    """은퇴일을 적는다. None 이면 지운다."""
    await session.execute(update(AiModel).where(AiModel.slug == slug).values(retires_on=on))
    await session.commit()
