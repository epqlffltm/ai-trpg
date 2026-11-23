# shared/reference-core/src/reference_core/finder.py

"""
대화 서버(chat, story)가 말 한 번에 참고 자료를 찾는 것. 모델을 부르기 직전에 한 번 돈다.

찾는 것은 reference_core/search.py 의 find_references 다. 여기는 대화를 막지 않게 감싼다.
  - FIND_SECONDS 안에 끝나지 않거나 실패하면 찾지 않은 것으로 한다(로그의 operation 은 서버가 정한다).
    사람은 첫 글자를 기다리는 중이다. 참고 자료가 없어도 대화는 돈다
  - 남은 자리가 없거나 찾는 글이 비었으면 아무것도 읽지 않는다
켰는지(제작자의 허용과 사람의 켜기)와 남은 자리는 서버가 정해 넘긴다.
게임 서버는 이것을 쓰지 않는다. 서술의 시간 상한이 따로 있다(app/references/retrieval.py).
"""

import asyncio
import logging
from dataclasses import dataclass

from ai_core.embedder import Embedder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reference_core.records import StoredReference
from reference_core.search import find_references
from reference_core.selection import ReferenceThresholds
from reference_core.tables import ReferenceTables

logger = logging.getLogger(__name__)

# 찾기 한 번의 시간 상한(초). 대화 서버의 로어북 찾기(RECALL_SECONDS)와 같다
FIND_SECONDS = 3.0


@dataclass(frozen=True)
class ReferenceFinder:
    """말 한 번에 참고 자료를 찾는 것. 서버가 앱에 하나 둔다. 임베더를 끄면 만들지 않는다."""

    tables: ReferenceTables
    session_factory: async_sessionmaker[AsyncSession]
    embedder: Embedder
    # 로그의 operation(chat.reference_find 등)
    operation: str
    thresholds: ReferenceThresholds = ReferenceThresholds()
    seconds: float = FIND_SECONDS

    async def find(self, text: str, room: int) -> list[StoredReference]:
        """찾는 글에 맞는 줄들. 자리가 없거나, 글이 비었거나, 시간이 다 되거나 실패하면 빈 목록이다."""
        if room <= 0 or not text.strip():
            return []
        try:
            return await asyncio.wait_for(self.search(text, room), self.seconds)
        except Exception:
            logger.warning('참고 자료를 찾지 못했습니다', exc_info=True, extra={'operation': self.operation})
            return []

    async def search(self, text: str, room: int) -> list[StoredReference]:
        """DB 와 임베딩 모델로 고른다. 자리는 room 과 설정의 상한 중 작은 것이다."""
        limit = min(room, self.thresholds.max_chars)
        return await find_references(self.tables, self.session_factory, self.embedder, text, self.thresholds, limit)
