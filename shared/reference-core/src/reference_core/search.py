# shared/reference-core/src/reference_core/search.py

"""
찾는 글 하나에 맞는 참고 자료를 DB 에서 고른다. 고르는 규칙은 reference_core/selection.py 다.

  1. 찾는 글을 벡터로 바꾼다(임베딩 모델). 이때는 DB 연결을 쥐지 않는다.
  2. 다른 이름이 글에 든 줄과, 그 줄들의 거리와, 뜻이 가까운 줄들을 읽는다(DB).
  3. 남은 자리(room) 안에서 고른다.
실패해도 부른 쪽(서술, 말 한 번)을 막지 않는다. 임베딩 모델이 실패하면 다른 이름으로만, 거리를 보지 않고 고른다.
벡터가 없는 자료(관리 명령의 index 를 아직 돌리지 않음)는 다른 이름으로만 걸린다.
켰는지, 남은 자리가 얼마인지는 서버가 정해 넘긴다.
"""

import logging
import uuid
from collections.abc import Sequence

from ai_core.embedder import Embedder
from ai_core.provider import ProviderError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reference_core import repository
from reference_core.records import StoredReference
from reference_core.selection import ReferenceThresholds, alias_hits, choose
from reference_core.tables import ReferenceTables

logger = logging.getLogger(__name__)


async def query_vector(embedder: Embedder, text: str) -> list[float] | None:
    """찾는 글의 벡터. 임베딩 모델이 실패하면 None 이다(다른 이름으로만 고른다). 이유만 로그에 남긴다."""
    try:
        (vector,) = await embedder.embed([text])
    except ProviderError as error:
        logger.warning('찾는 글을 벡터로 바꾸지 못했다(%s). 참고 자료는 다른 이름으로만 고른다', error)
        return None
    return vector


async def measure(
    tables: ReferenceTables,
    session: AsyncSession,
    model: str,
    vector: list[float] | None,
    hits: Sequence[StoredReference],
    thresholds: ReferenceThresholds,
) -> tuple[dict[uuid.UUID, float], list[StoredReference]]:
    """다른 이름으로 걸린 줄들의 거리와, 뜻이 가까운 줄들. 벡터가 없으면 둘 다 비어 있다."""
    if vector is None:
        return {}, []
    distances = await repository.distances_of(tables, session, model, vector, [hit.id for hit in hits])
    found = await repository.nearest(tables, session, model, vector, thresholds.max_distance, thresholds.limit)
    return distances, [reference for reference, _ in found]


async def find_references(
    tables: ReferenceTables,
    session_factory: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    text: str,
    thresholds: ReferenceThresholds,
    room: int,
) -> list[StoredReference]:
    """찾는 글에 맞는 줄들. 남은 자리가 없으면 아무것도 읽지 않고 빈 목록이다."""
    if room <= 0:
        return []
    vector = await query_vector(embedder, text)
    async with session_factory() as session:
        hits = alias_hits(await repository.list_aliased(tables, session), text)
        distances, nearest = await measure(tables, session, embedder.model, vector, hits, thresholds)
    return choose(hits, distances, nearest, thresholds, room)
