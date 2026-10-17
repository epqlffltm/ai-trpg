# game-server/app/memory/indexing.py

"""
테이블의 지난 라운드를 벡터로 바꿔 저장한다(색인). 서술을 맡길 때 모자라면 뒤에서 돈다(app/memory/retrieval.py).

로어북의 색인(app/lore/indexing.py)과 같은 모양이다. 하는 일 셋을 한 함수에 섞지 않는다.
  1. 테이블에서 아직 벡터가 없는 기억을 고른다(DB 를 읽는다).
  2. 임베딩 모델을 부른다. 이때는 DB 연결을 쥐고 있지 않다.
  3. 받은 벡터를 저장한다(DB 에 쓴다).

라운드가 닫힐 때마다 맡기지 않고, 다음 서술을 맡길 때 모자란 것을 맡긴다. 검색하는 기억은 지난 기록(최근 3 라운드)보다
앞의 것이라, 방금 닫힌 라운드의 벡터는 몇 라운드 뒤에야 쓰인다. 그 사이에 만들어진다.
실패해도 게임은 진행된다. 벡터가 없는 기억은 키워드로만 찾아진다. 다음 서술 때 다시 맡긴다.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.provider import ProviderError
from app.core.jobs import BackgroundJobs
from app.lore.texts import batched
from app.memory import repository
from app.memory.texts import Memory, memories_of, memory_text, missing_memories
from app.rounds.narration_request import to_past

logger = logging.getLogger(__name__)

# 색인을 맡은 작업의 종류. 로그의 operation 이고, 동시에 도는 수를 이 종류로 센다(app/core/jobs.py)
INDEX_OPERATION = 'memory.index'
# 색인이 돌거나 기다리는 수의 상한. 넘으면 맡지 않는다. 다음에 검색할 때 벡터가 모자란 것을 보고 다시 맡긴다
INDEX_CAPACITY = 50


async def load_missing(
    session_factory: async_sessionmaker[AsyncSession], table_id: uuid.UUID, model: str
) -> list[Memory]:
    """테이블의 기억 중 이 모델의 벡터가 아직 없는 것들. 테이블이 없으면 빈 목록이다."""
    async with session_factory() as session:
        rounds = [to_past(round_) for round_ in await repository.list_rounds_until(session, table_id)]
        done = await repository.indexed_numbers(session, table_id, model)
    return missing_memories(memories_of(rounds), done)


async def save_vectors(
    session_factory: async_sessionmaker[AsyncSession],
    table_id: uuid.UUID,
    model: str,
    memories: list[Memory],
    vectors: list[list[float]],
) -> None:
    """기억들의 벡터를 세션을 따로 열어 저장한다. memories 와 vectors 는 같은 차례다."""
    async with session_factory() as session:
        by_number = {memory.number: vector for memory, vector in zip(memories, vectors, strict=True)}
        await repository.add_vectors(session, table_id, model, by_number)
        await session.commit()


async def index_table(
    session_factory: async_sessionmaker[AsyncSession], embedder: Embedder, table_id: uuid.UUID
) -> int:
    """
    테이블의 기억 중 벡터가 없는 것을 만들어 저장한다. 새로 만든 수를 돌려준다.

    이미 다 있으면 모델을 부르지 않는다. 여러 번 불러도 같은 결과다.
    모델이 실패하면 거기서 멈추고 그때까지 만든 수를 돌려준다. 이유(timeout 등)만 로그에 남긴다.
    """
    missing = await load_missing(session_factory, table_id, embedder.model)
    added = 0
    for batch in batched(missing):
        try:
            vectors = await embedder.embed([memory_text(memory) for memory in batch])
        except ProviderError as error:
            logger.warning(
                '지난 라운드의 벡터를 만들지 못했다(테이블 %s, %s). 남은 것은 다음에 만든다', table_id, error
            )
            return added
        await save_vectors(session_factory, table_id, embedder.model, batch, vectors)
        added += len(batch)
    return added


@dataclass(frozen=True)
class MemoryIndexer:
    """테이블의 색인을 뒤에서 돌게 맡기는 것. 앱에 하나 둔다(app/main.py)."""

    session_factory: async_sessionmaker[AsyncSession]
    embedder: Embedder
    jobs: BackgroundJobs

    def schedule(self, table_id: uuid.UUID) -> None:
        """
        이 테이블의 색인을 맡긴다. 기다리지 않고 바로 돌아온다.

        같은 테이블의 색인이 이미 돌거나 기다리면 맡지 않는다. 검색할 때마다 벡터가 모자라면 다시 맡기므로,
        임베딩 모델이 죽어 있는 동안 같은 색인이 겹겹이 쌓이지 않게 한다. 같은 것을 두 번 해도 결과는 같다.
        """
        job = index_table(self.session_factory, self.embedder, table_id)
        self.jobs.spawn_once(job, name=f'index-memories:{table_id}', operation=INDEX_OPERATION)
