# trpg-server/app/references/retrieval.py

"""
서술하기 직전에 이번 장면에 맞는 참고 자료(#482)를 고른다. 고른 것은 프롬프트의 [참고 자료]에 들어간다.

고르는 규칙과 DB 에서 찾는 것은 공용 코드에 있다(reference_core/selection.py, reference_core/search.py).
chat, story 와 같다.
여기는 게임 서버가 정하는 것만 한다.
  - 테이블이 켰을 때만 고른다(game_tables.references_enabled). 켤 수 있는지는 세계관이 정한다(app/references/policy.py).
  - 제작자의 자산이 늘 먼저다. 로어북 항목을 고른 뒤 남은 글자 수(LORE_MAX_CHARS)에만 넣는다(room_for).
    그 안에서도 REFERENCE_MAX_CHARS 를 넘지 않는다. 입력 예산을 넘으면 로어북보다 먼저 뺀다(app/rounds/budget.py).
    그래서 값을 더 받지 않는다. 원가가 판매가가 가정한 입력 안에 든다(2026-10-21 유저 결정).
  - 찾는 글은 로어북 검색과 같다(장면과 선언, app/lore/retrieval.py 의 query_text).
  - 서술에만 쓴다. 글에는 수치가 없고, 판정에는 끼지 않는다.
"""

import uuid
from dataclasses import dataclass

from ai_core.embedder import Embedder
from reference_core.records import StoredReference
from reference_core.search import find_references
from reference_core.selection import REFERENCE_MAX_CHARS, ReferenceThresholds
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.catalog.steps import scaled_chars
from app.lore.retrieval import lore_max_chars, query_text
from app.references.models import TABLES
from app.rounds.narrator import NarrationRequest, ReferenceNote
from app.tables import repository as table_repository


def room_for(request: NarrationRequest, max_chars: int = REFERENCE_MAX_CHARS) -> int:
    """
    참고 자료에 쓸 수 있는 글자 수. 로어북이 쓰고 남은 것과 max_chars 중 작은 것이다. 남은 것이 없으면 0 이다.

    max_chars 는 기본 단계의 상한이다. 둘 다 요청의 입력 단계만큼 는다(#387).
    """
    used = sum(len(note.name) + len(note.content) for note in request.lore)
    return max(0, min(scaled_chars(max_chars, request.steps), lore_max_chars(request.steps) - used))


def to_reference_note(reference: StoredReference) -> ReferenceNote:
    """고른 줄을 서술자에게 줄 모양으로. 한국어로 옮긴 이름과 글이 있으면 그것이다."""
    return ReferenceNote(
        reference_id=reference.id, name=reference.shown_name, content=reference.shown_content, kind=reference.kind
    )


@dataclass(frozen=True)
class ReferenceRetriever:
    """
    서술하기 직전에 참고 자료를 고르는 것. closing.ReferenceFinder 의 구현이다.

    앱에 하나 둔다(app/main.py). 임베더는 색인(scripts/references.py index)과 같은 모델이어야 한다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    embedder: Embedder
    thresholds: ReferenceThresholds = ReferenceThresholds()

    async def find(self, request: NarrationRequest) -> list[ReferenceNote]:
        """이번 장면에 맞는 참고 자료. 테이블이 켜지 않았거나, 남은 자리가 없으면 빈 목록이다."""
        room = room_for(request, self.thresholds.max_chars)
        if request.table_id is None or room == 0 or not await self.enabled(request.table_id):
            return []
        chosen = await find_references(
            TABLES, self.session_factory, self.embedder, query_text(request), self.thresholds, room
        )
        return [to_reference_note(reference) for reference in chosen]

    async def enabled(self, table_id: uuid.UUID) -> bool:
        """이 테이블이 참고 자료를 켰는가. 테이블이 없으면 False."""
        async with self.session_factory() as session:
            table = await table_repository.find_table(session, table_id)
        return table is not None and table.references_enabled
