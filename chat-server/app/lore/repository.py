# chat-server/app/lore/repository.py

"""
로어북 항목의 벡터를 DB 에서 읽고 쓴다. 커밋하지 않는다.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import ImportedCharacter
from app.lore.models import LoreEmbedding
from app.lore.texts import EntryKey


async def find_character(session: AsyncSession, character_id: uuid.UUID) -> ImportedCharacter | None:
    """판의 사본 하나. 없으면(지웠다) None."""
    return await session.get(ImportedCharacter, character_id)


async def done_keys(session: AsyncSession, character_id: uuid.UUID, model: str) -> set[EntryKey]:
    """이 사본, 이 모델로 이미 벡터가 있는 항목들의 열쇠."""
    query = select(LoreEmbedding.lorebook_id, LoreEmbedding.entry_id).where(
        LoreEmbedding.character_id == character_id, LoreEmbedding.model == model
    )
    return {(lorebook_id, entry_id) for lorebook_id, entry_id in await session.execute(query)}


async def add_embeddings(
    session: AsyncSession, character_id: uuid.UUID, model: str, vectors: list[tuple[EntryKey, list[float]]]
) -> None:
    """벡터들을 적는다. 이미 있는 것(다른 작업이 먼저 적었다)은 그대로 둔다."""
    if not vectors:
        return
    rows = [
        {'character_id': character_id, 'model': model, 'lorebook_id': key[0], 'entry_id': key[1], 'embedding': vector}
        for key, vector in vectors
    ]
    await session.execute(insert(LoreEmbedding).values(rows).on_conflict_do_nothing())


async def entry_distances(
    session: AsyncSession, character_id: uuid.UUID, model: str, vector: list[float]
) -> dict[EntryKey, float]:
    """
    이 사본, 이 모델의 벡터마다 vector 와의 거리. 거리는 코사인 거리다(0 이면 같은 방향, 1 이면 직각, 2 면 반대).
    색인 없이 사본의 벡터를 모두 견준다(많아야 600 개). 고르는 규칙은 app/lore/recall.py 의 순수 함수가 정한다.
    """
    distance = LoreEmbedding.embedding.cosine_distance(vector)
    query = select(LoreEmbedding.lorebook_id, LoreEmbedding.entry_id, distance).where(
        LoreEmbedding.character_id == character_id, LoreEmbedding.model == model
    )
    return {(lorebook_id, entry_id): float(value) for lorebook_id, entry_id, value in await session.execute(query)}
