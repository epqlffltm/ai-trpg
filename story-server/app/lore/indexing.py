# story-server/app/lore/indexing.py

"""
판의 사본에 든 로어북 항목을 벡터로 바꿔 둔다. 응답과 따로 도는 작업이다(chat 과 같다).

  - 세션을 시작하면 그 사본을 맡긴다(app/conversations/router.py). 찾을 때 벡터가 모자라도 맡긴다(app/lore/recall.py)
  - 아직 벡터가 없는 항목만 BATCH_SIZE 개씩 바꾼다. 같은 사본은 이 서버 안에서 한 번에 하나만 돈다.
    서버가 여럿이어서 함께 돌아도 같은 줄은 하나만 남는다(유일 제약)
  - 임베딩 모델을 부르는 동안 DB 의 연결을 쥐지 않는다. 묶음마다 짧게 적는다
  - 실패하면 로그(story.lore_index)만 남긴다. 그동안 말은 상시와 키워드로 돈다. 다음에 찾을 때 다시 맡긴다
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from ai_core.embedder import Embedder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.lore import repository
from app.lore.texts import KeyedEntry, batches, entry_text, keyed_entries, missing_entries
from app.turns.briefing import read_briefing

logger = logging.getLogger(__name__)

# 로그의 operation
INDEX_OPERATION = 'story.lore_index'


@dataclass
class LoreIndexer:
    """벡터를 만드는 작업. 앱에 하나 둔다(app.state.lore_indexer)."""

    session_factory: async_sessionmaker[AsyncSession]
    embedder: Embedder
    running: set[uuid.UUID] = field(default_factory=set)
    tasks: set[asyncio.Task] = field(default_factory=set)

    def request(self, world_id: uuid.UUID) -> None:
        """그 사본의 벡터를 채우러 간다(따로 돈다). 이미 채우는 중이면 하지 않는다."""
        if world_id in self.running:
            return
        self.running.add(world_id)
        task = asyncio.create_task(self.index(world_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(lambda _: self.running.discard(world_id))

    async def index(self, world_id: uuid.UUID) -> int:
        """벡터를 채운다. 새로 적은 수. 실패는 로그에 남기고 0 이다."""
        try:
            return await self.fill(world_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                '로어북의 벡터를 만들지 못했습니다', extra={'operation': INDEX_OPERATION, 'world_id': str(world_id)}
            )
            return 0

    async def missing(self, world_id: uuid.UUID) -> list[KeyedEntry]:
        """아직 벡터가 없는 항목들. 사본이 없으면(지웠다) 빈 목록이다."""
        async with self.session_factory() as session:
            world = await repository.find_world(session, world_id)
            if world is None:
                return []
            done = await repository.done_keys(session, world_id, self.embedder.model)
        return missing_entries(keyed_entries(read_briefing(world.document)), done)

    async def fill(self, world_id: uuid.UUID) -> int:
        """모자란 항목을 묶음마다 벡터로 바꿔 적는다. 적은 수를 돌려준다."""
        written = 0
        for batch in batches(await self.missing(world_id)):
            vectors = await self.embedder.embed([entry_text(keyed.entry) for keyed in batch])
            async with self.session_factory() as session:
                pairs = [(keyed.key, vector) for keyed, vector in zip(batch, vectors, strict=True)]
                await repository.add_embeddings(session, world_id, self.embedder.model, pairs)
                await session.commit()
            written += len(batch)
        return written

    async def stop(self) -> None:
        """도는 작업을 모두 멈추고 끝나기를 기다린다. 서버가 꺼질 때 부른다."""
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
