# game-server/app/lore/repository.py

"""로어북 항목의 벡터를 읽고 쓰는 쿼리. 커밋은 부르는 쪽이 한다."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import ScenarioVersion
from app.lore.models import LoreEmbedding


async def find_version(session: AsyncSession, version_id: uuid.UUID) -> ScenarioVersion | None:
    """판 하나. 없으면 None."""
    return await session.get(ScenarioVersion, version_id)


async def list_version_ids(session: AsyncSession) -> list[uuid.UUID]:
    """모든 판의 id. 오래된 것부터다. 벡터를 한꺼번에 다시 만들 때 쓴다(scripts/index_lore.py)."""
    result = await session.scalars(select(ScenarioVersion.id).order_by(ScenarioVersion.created_at))
    return list(result)


async def indexed_entry_ids(session: AsyncSession, version_id: uuid.UUID, model: str) -> set[uuid.UUID]:
    """이 판의 항목 중 이 모델의 벡터가 이미 있는 것들의 id."""
    query = select(LoreEmbedding.entry_id).where(LoreEmbedding.version_id == version_id, LoreEmbedding.model == model)
    return set(await session.scalars(query))


async def add_embeddings(
    session: AsyncSession, version_id: uuid.UUID, model: str, vectors: dict[uuid.UUID, list[float]]
) -> None:
    """
    항목들의 벡터를 넣는다. vectors 는 항목의 id 에서 벡터로.

    이미 있는 것(같은 판, 모델, 항목)은 건너뛴다. 두 작업이 같은 판을 함께 만들어도 실패하지 않는다.
    """
    if not vectors:
        return
    rows = [
        {'version_id': version_id, 'model': model, 'entry_id': entry_id, 'embedding': vector}
        for entry_id, vector in vectors.items()
    ]
    statement = insert(LoreEmbedding).values(rows).on_conflict_do_nothing()
    await session.execute(statement)


async def count_vectors(session: AsyncSession, version_id: uuid.UUID, model: str) -> int:
    """이 판, 이 모델의 벡터가 몇 개인가."""
    query = select(func.count()).where(LoreEmbedding.version_id == version_id, LoreEmbedding.model == model)
    return await session.scalar(query) or 0


async def nearest_entry_ids(
    session: AsyncSession, version_id: uuid.UUID, model: str, vector: list[float], limit: int, max_distance: float
) -> list[uuid.UUID]:
    """
    이 판, 이 모델의 벡터 중 vector 와 가까운 항목들의 id. 가까운 것부터 limit 개까지, 거리가 max_distance 이하인 것만.

    거리는 코사인 거리다(0 이면 같은 방향, 1 이면 직각, 2 면 반대). 색인 없이 판의 벡터를 모두 견준다.
    """
    distance = LoreEmbedding.embedding.cosine_distance(vector)
    query = (
        select(LoreEmbedding.entry_id)
        .where(LoreEmbedding.version_id == version_id, LoreEmbedding.model == model, distance <= max_distance)
        .order_by(distance)
        .limit(limit)
    )
    return list(await session.scalars(query))
