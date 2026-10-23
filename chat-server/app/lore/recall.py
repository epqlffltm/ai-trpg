# chat-server/app/lore/recall.py

"""
로어북에서 뜻으로 찾는다(#672, 하이브리드의 벡터 쪽). 말 한 번에 한 번, 모델을 부르기 직전에 돈다.

  - 찾는 글(최근 말 둘)을 벡터로 바꾸고, 그 사본의 항목 벡터와의 코사인 거리를 잰다
  - MAX_DISTANCE 안에서 가까운 것부터 RECALL_MAX 개. 상시와 키워드로 이미 고른 것은 뺀다
  - RECALL_SECONDS 안에 끝나지 않거나 실패하면 찾지 않은 것으로 한다(로그 chat.lore_recall). 대화는 상시와 키워드로 돈다
  - 사본의 벡터가 없거나 모자라면 만들기를 맡긴다(app/lore/indexing.py). 이번에는 있는 것만 쓴다
임베딩 모델을 부르는 동안 DB 의 연결을 쥐지 않는다.
"""

import asyncio
import logging
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from ai_core.embedder import Embedder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.lore import repository
from app.lore.indexing import LoreIndexer
from app.lore.texts import EntryKey
from app.turns.values import LorePlan

logger = logging.getLogger(__name__)

# 로그의 operation
RECALL_OPERATION = 'chat.lore_recall'
# 말 한 번의 찾기의 시간 상한(초). 사람은 첫 글자를 기다리는 중이다
RECALL_SECONDS = 3.0
# 받아들이는 거리의 상한(코사인 거리). trpg-server 의 로어북(LORE_MAX_DISTANCE)과 같다
MAX_DISTANCE = 0.45
# 뜻으로 찾아 더하는 항목의 수
RECALL_MAX = 3


def nearest(
    keys: Sequence[EntryKey], distances: Mapping[EntryKey, float], exclude: Collection[int], limit: int = RECALL_MAX
) -> list[int]:
    """가까운 항목의 자리들. 거리 MAX_DISTANCE 안에서 가까운 것부터(같으면 판의 차례) limit 개. exclude 는 뺀다."""
    scored = [
        (distances[key], index)
        for index, key in enumerate(keys)
        if index not in exclude and key in distances and distances[key] <= MAX_DISTANCE
    ]
    return [index for _, index in sorted(scored)[:limit]]


@dataclass
class LoreRecall:
    """뜻으로 찾는 것. 앱에 하나 둔다(app.state.lore_recall). 임베더를 끄면 없다."""

    session_factory: async_sessionmaker[AsyncSession]
    embedder: Embedder
    indexer: LoreIndexer

    async def recall(self, plan: LorePlan) -> list[int]:
        """뜻으로 찾은 항목의 자리들. 시간이 다 되거나 실패하면 빈 목록이다."""
        try:
            return await asyncio.wait_for(self.search(plan), RECALL_SECONDS)
        except Exception:
            logger.warning(
                '로어북을 뜻으로 찾지 못했습니다',
                exc_info=True,
                extra={'operation': RECALL_OPERATION, 'character_id': str(plan.character_id)},
            )
            return []

    async def search(self, plan: LorePlan) -> list[int]:
        """찾는 글을 벡터로 바꾸고 가까운 항목을 고른다. 벡터가 모자라면 만들기를 맡긴다."""
        vector = (await self.embedder.embed([plan.query]))[0]
        async with self.session_factory() as session:
            distances = await repository.entry_distances(session, plan.character_id, self.embedder.model, vector)
        if len(distances) < len(set(plan.keys)):
            self.indexer.request(plan.character_id)
        return nearest(plan.keys, distances, plan.ranked)
