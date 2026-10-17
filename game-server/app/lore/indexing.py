# game-server/app/lore/indexing.py

"""
게시한 판의 로어북 항목을 벡터로 바꿔 저장한다(색인). 게시 직후 뒤에서 돈다.

하는 일은 셋이다. 셋을 한 함수에 섞지 않는다.
  1. 판에서 아직 벡터가 없는 항목을 고른다(DB 를 읽는다).
  2. 임베딩 모델을 부른다. 이때는 DB 연결을 쥐고 있지 않다.
  3. 받은 벡터를 저장한다(DB 에 쓴다).
묶음(32개)마다 부르고 바로 저장한다. 중간에 실패해도 앞의 묶음은 남고, 다음에 남은 것부터 만든다.

실패해도 게시는 이미 끝났다. 벡터가 없는 동안 검색은 키워드로만 찾는다(RAG ②).
임베딩 모델의 실패(ProviderError)는 로그에 남기고 그만둔다. 그 밖의 예외는 버그다. 작업을 돌리는 쪽이 로그에 남긴다.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.provider import ProviderError
from app.assets.scenarios.snapshot import EntrySnapshot, read_snapshot
from app.core.jobs import BackgroundJobs
from app.lore import repository
from app.lore.texts import batched, entry_text, missing_entries, version_entries

logger = logging.getLogger(__name__)

# 색인을 맡은 작업의 종류. 로그의 operation 이고, 동시에 도는 수를 이 종류로 센다(app/core/jobs.py)
INDEX_OPERATION = 'lore.index'
# 색인이 돌거나 기다리는 수의 상한. 넘으면 맡지 않는다. 다음에 검색할 때 벡터가 모자란 것을 보고 다시 맡긴다
INDEX_CAPACITY = 50


async def load_missing(
    session_factory: async_sessionmaker[AsyncSession], version_id: uuid.UUID, model: str
) -> list[EntrySnapshot]:
    """판에서 이 모델의 벡터가 아직 없는 항목들. 판이 없으면 빈 목록이다."""
    async with session_factory() as session:
        version = await repository.find_version(session, version_id)
        if version is None:
            return []
        entries = version_entries(read_snapshot(version.snapshot))
        done = await repository.indexed_entry_ids(session, version_id, model)
    return missing_entries(entries, done)


async def save_vectors(
    session_factory: async_sessionmaker[AsyncSession],
    version_id: uuid.UUID,
    model: str,
    entries: list[EntrySnapshot],
    vectors: list[list[float]],
) -> None:
    """항목들의 벡터를 세션을 따로 열어 저장한다. entries 와 vectors 는 같은 차례다."""
    async with session_factory() as session:
        by_entry = {entry.id: vector for entry, vector in zip(entries, vectors, strict=True)}
        await repository.add_embeddings(session, version_id, model, by_entry)
        await session.commit()


async def index_version(
    session_factory: async_sessionmaker[AsyncSession], embedder: Embedder, version_id: uuid.UUID
) -> int:
    """
    판의 항목 중 벡터가 없는 것을 만들어 저장한다. 새로 만든 수를 돌려준다.

    이미 다 있으면 모델을 부르지 않는다. 여러 번 불러도 같은 결과다.
    모델이 실패하면 거기서 멈추고 그때까지 만든 수를 돌려준다. 이유(timeout 등)만 로그에 남긴다.
    """
    missing = await load_missing(session_factory, version_id, embedder.model)
    added = 0
    for batch in batched(missing):
        try:
            vectors = await embedder.embed([entry_text(entry) for entry in batch])
        except ProviderError as error:
            logger.warning('로어북 항목의 벡터를 만들지 못했다(판 %s, %s). 남은 것은 다음에 만든다', version_id, error)
            return added
        await save_vectors(session_factory, version_id, embedder.model, batch, vectors)
        added += len(batch)
    return added


@dataclass(frozen=True)
class LoreIndexer:
    """
    판의 색인을 뒤에서 돌게 맡기는 것. publishing.VersionIndexer 의 구현이다.

    요청마다 하나 만든다(app/assets/scenarios/router.py). 그때 앱에 꽂혀 있는 임베더를 쓴다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    embedder: Embedder
    jobs: BackgroundJobs

    def schedule(self, version_id: uuid.UUID) -> None:
        """
        이 판의 색인을 맡긴다. 기다리지 않고 바로 돌아온다.

        같은 판의 색인이 이미 돌거나 기다리면 맡지 않는다. 검색할 때마다 벡터가 모자라면 다시 맡기므로,
        임베딩 모델이 죽어 있는 동안 같은 색인이 겹겹이 쌓이지 않게 한다. 같은 것을 두 번 해도 결과는 같다.
        """
        job = index_version(self.session_factory, self.embedder, version_id)
        self.jobs.spawn_once(job, name=f'index-lore:{version_id}', operation=INDEX_OPERATION)
