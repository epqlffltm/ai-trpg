# trpg-server/app/references/retrieval.py

"""
서술하기 직전에 이번 장면에 맞는 참고 자료(#482)를 고른다. 고른 것은 프롬프트의 [참고 자료]에 들어간다.

로어북 검색(app/lore/retrieval.py)과 같은 방식이다. 찾는 글(장면과 선언)을 벡터로 바꿔 자료의 벡터와의 거리를 잰다.
  1. 다른 이름: 줄의 다른 이름(한국어 이름, aliases)이 글에 그대로 들어 있고, 거리가 keyword_max_distance 이하인 것.
     원본의 이름(영어)으로는 고르지 않는다. 한국어 장면에 나오지 않고, 짧은 영어 이름("Bat")은 낱말 속에서 잘못 걸린다.
  2. 벡터: 거리가 max_distance 이하인 것, 가까운 순으로 limit 개까지.
다른 이름으로 고른 것을 먼저, 그다음 가까운 순으로 넣는다.

정한 것(2026-10-21 유저 결정과 #482).
  - 테이블이 켰을 때만 고른다(game_tables.references_enabled). 켤 수 있는지는 세계관이 정한다(app/references/policy.py).
  - 제작자의 자산이 늘 먼저다. 로어북 항목을 고른 뒤 남은 글자 수(LORE_MAX_CHARS)에만 넣는다.
    그 안에서도 REFERENCE_MAX_CHARS 를 넘지 않는다. 입력 예산을 넘으면 로어북보다 먼저 뺀다(app/rounds/budget.py).
    그래서 값을 더 받지 않는다. 원가가 판매가가 가정한 입력 안에 든다.
  - 서술에만 쓴다. 글에는 수치가 없고, 판정에는 끼지 않는다.

실패해도 서술을 막지 않는다. 임베딩 모델이 실패하면 다른 이름으로만, 거리를 보지 않고 고른다.
벡터가 없는 자료(관리 명령의 index 를 아직 돌리지 않음)는 다른 이름으로만 걸린다.
"""

import logging
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ai_core.embedder import Embedder
from ai_core.provider import ProviderError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.lore.retrieval import LORE_MAX_CHARS, query_text
from app.references import repository
from app.references.records import StoredReference
from app.rounds.narrator import NarrationRequest, ReferenceNote
from app.tables import repository as table_repository

logger = logging.getLogger(__name__)

# 넣는 참고 자료의 글자 수(이름 + 글)의 합의 상한. 한 줄이 1,000자 안쪽이라 한두 줄이다
REFERENCE_MAX_CHARS = 1500
# 넣는 참고 자료의 수의 상한
REFERENCE_LIMIT = 3
# 이보다 짧은 다른 이름으로는 고르지 않는다
MIN_ALIAS_LENGTH = 2
# 이보다 먼 줄은 벡터로 고르지 않는다. 설정 REFERENCE_MAX_DISTANCE 의 기본값. 로어북의 것(bge-m3)과 같게 두었다.
# 자료가 영어라 한국어 장면과의 거리는 로어북보다 멀 수 있다. 켠 것과 끈 것을 견주는 평가(#482 3단계)로 다시 잰다
MAX_DISTANCE = 0.45
# 다른 이름으로 걸린 줄도 거리가 이보다 멀면 넣지 않는다(동음이의어). 설정 REFERENCE_KEYWORD_MAX_DISTANCE 의 기본값
KEYWORD_MAX_DISTANCE = 0.50


@dataclass(frozen=True)
class ReferenceThresholds:
    """고르는 규칙의 숫자들. 거리는 코사인 거리다."""

    max_distance: float = MAX_DISTANCE
    keyword_max_distance: float = KEYWORD_MAX_DISTANCE
    limit: int = REFERENCE_LIMIT
    max_chars: int = REFERENCE_MAX_CHARS


def room_for(request: NarrationRequest, max_chars: int = REFERENCE_MAX_CHARS) -> int:
    """참고 자료에 쓸 수 있는 글자 수. 로어북이 쓰고 남은 것과 max_chars 중 작은 것이다. 남은 것이 없으면 0 이다."""
    used = sum(len(note.name) + len(note.content) for note in request.lore)
    return max(0, min(max_chars, LORE_MAX_CHARS - used))


def mentions_alias(reference: StoredReference, text: str) -> bool:
    """
    줄의 다른 이름 중 하나가 글에 그대로 들어 있는가. 대소문자는 가리지 않는다.

    한 글자 이름("쥐")은 보지 않는다. 낱말 속("쥐었다")에서 잘못 걸린다. 그런 줄은 뜻(벡터)으로 고른다.
    """
    folded = text.casefold()
    names = [alias.strip() for alias in reference.aliases]
    return any(name.casefold() in folded for name in names if len(name) >= MIN_ALIAS_LENGTH)


def alias_hits(references: Sequence[StoredReference], text: str) -> list[StoredReference]:
    """다른 이름이 글에 들어 있는 줄들. 받은 차례대로다."""
    return [reference for reference in references if mentions_alias(reference, text)]


def near_enough(reference: StoredReference, distances: Mapping[uuid.UUID, float], max_distance: float) -> bool:
    """다른 이름으로 걸린 줄을 넣어도 되는가. 거리가 max_distance 이하이거나, 거리를 모르면(벡터가 없음) 넣는다."""
    return distances.get(reference.id, -math.inf) <= max_distance


def reference_size(reference: StoredReference) -> int:
    """줄 하나가 서술에 차지하는 글자 수(이름 + 글). 로어북 항목과 같은 셈이다(app/lore/retrieval.py 의 note_size)."""
    return len(reference.shown_name) + len(reference.shown_content)


def pick(ordered: Sequence[StoredReference], room: int, limit: int) -> list[StoredReference]:
    """
    차례대로 넣되 글자 수의 합이 room 을, 수가 limit 을 넘지 않게 고른다. 같은 줄은 한 번만.

    들어가지 않는 줄은 건너뛰고 다음 것을 본다. 뒤의 짧은 줄은 들어갈 수 있다.
    """
    picked: list[StoredReference] = []
    seen: set[uuid.UUID] = set()
    used = 0
    for reference in ordered:
        size = reference_size(reference)
        if len(picked) >= limit:
            break
        if reference.id in seen or used + size > room:
            continue
        picked.append(reference)
        seen.add(reference.id)
        used += size
    return picked


def choose(
    hits: Sequence[StoredReference],
    distances: Mapping[uuid.UUID, float],
    nearest: Sequence[StoredReference],
    thresholds: ReferenceThresholds,
    room: int,
) -> list[StoredReference]:
    """
    넣을 줄을 고른다. 다른 이름으로 걸리고 거리가 가까운 것을 먼저, 그다음 뜻이 가까운 것(nearest)을, room 안에서.

    nearest 는 이미 거리 기준 안의 가까운 순이다(repository.nearest). distances 는 다른 이름으로 걸린 줄의 거리다.
    """
    near_hits = [hit for hit in hits if near_enough(hit, distances, thresholds.keyword_max_distance)]
    return pick([*near_hits, *nearest], room, thresholds.limit)


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
        text = query_text(request)
        vector = await self.query_vector(text)
        async with self.session_factory() as session:
            hits = alias_hits(await repository.list_aliased(session), text)
            distances, nearest = await self.measure(session, vector, hits)
        return [to_reference_note(reference) for reference in choose(hits, distances, nearest, self.thresholds, room)]

    async def enabled(self, table_id: uuid.UUID) -> bool:
        """이 테이블이 참고 자료를 켰는가. 테이블이 없으면 False."""
        async with self.session_factory() as session:
            table = await table_repository.find_table(session, table_id)
        return table is not None and table.references_enabled

    async def query_vector(self, text: str) -> list[float] | None:
        """찾는 글의 벡터. 임베딩 모델이 실패하면 None 이다(다른 이름으로만 고른다). 이유만 로그에 남긴다."""
        try:
            (vector,) = await self.embedder.embed([text])
        except ProviderError as error:
            logger.warning('찾는 글을 벡터로 바꾸지 못했다(%s). 참고 자료는 다른 이름으로만 고른다', error)
            return None
        return vector

    async def measure(
        self, session: AsyncSession, vector: list[float] | None, hits: Sequence[StoredReference]
    ) -> tuple[dict[uuid.UUID, float], list[StoredReference]]:
        """다른 이름으로 걸린 줄들의 거리와, 뜻이 가까운 줄들. 벡터가 없으면 둘 다 비어 있다."""
        if vector is None:
            return {}, []
        model = self.embedder.model
        distances = await repository.distances_of(session, model, vector, [hit.id for hit in hits])
        found = await repository.nearest(session, model, vector, self.thresholds.max_distance, self.thresholds.limit)
        return distances, [reference for reference, _ in found]
