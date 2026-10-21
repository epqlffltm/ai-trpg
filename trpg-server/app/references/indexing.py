# trpg-server/app/references/indexing.py

"""
참고 자료의 줄들을 벡터로 바꿔 저장한다(색인). 관리 명령(scripts/references.py index)이 부른다.

로어북의 색인(app/lore/indexing.py)과 같은 방식이다.
  1. 이 모델의 벡터가 아직 없는 줄을 고른다(DB 를 읽는다).
  2. 임베딩 모델을 부른다. 이때는 DB 연결을 쥐고 있지 않다.
  3. 받은 벡터를 저장한다(DB 에 쓴다).
묶음(32개)마다 부르고 바로 저장한다. 중간에 실패해도 앞의 묶음은 남고, 다시 돌리면 남은 것부터 만든다.
임베딩 모델의 실패(ProviderError)는 로그에 남기고 그만둔다.
"""

import logging
from dataclasses import dataclass

from ai_core.embedder import Embedder
from ai_core.provider import ProviderError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.lore.texts import batched
from app.references import repository
from app.references.records import StoredReference
from app.references.texts import reference_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexResult:
    """색인 한 번의 결과. added 는 새로 만든 수, left 는 아직 벡터가 없는 수다(실패하면 0 보다 크다)."""

    added: int
    left: int


async def load_missing(session_factory: async_sessionmaker[AsyncSession], model: str) -> list[StoredReference]:
    """이 모델의 벡터가 아직 없는 줄들."""
    async with session_factory() as session:
        return await repository.list_missing(session, model)


async def save_vectors(
    session_factory: async_sessionmaker[AsyncSession],
    model: str,
    references: list[StoredReference],
    vectors: list[list[float]],
) -> None:
    """줄들의 벡터를 세션을 따로 열어 저장한다. references 와 vectors 는 같은 차례다."""
    async with session_factory() as session:
        by_reference = {reference.id: vector for reference, vector in zip(references, vectors, strict=True)}
        await repository.add_embeddings(session, model, by_reference)
        await session.commit()


async def index_references(session_factory: async_sessionmaker[AsyncSession], embedder: Embedder) -> IndexResult:
    """
    벡터가 없는 줄을 모두 만들어 저장한다. 이미 다 있으면 모델을 부르지 않는다. 여러 번 불러도 같은 결과다.

    모델이 실패하면 거기서 멈춘다. 그때까지 만든 수와 남은 수를 돌려준다.
    """
    missing = await load_missing(session_factory, embedder.model)
    added = 0
    for batch in batched(missing):
        try:
            vectors = await embedder.embed([reference_text(reference) for reference in batch])
        except ProviderError as error:
            logger.warning('참고 자료의 벡터를 만들지 못했다(%s). 남은 것은 다음에 만든다', error)
            break
        await save_vectors(session_factory, embedder.model, batch, vectors)
        added += len(batch)
    return IndexResult(added=added, left=len(missing) - added)
