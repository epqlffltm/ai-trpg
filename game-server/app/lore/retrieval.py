# game-server/app/lore/retrieval.py

"""
서술하기 직전에 이번 장면에 맞는 로어북 항목을 고른다(검색). 고른 항목은 프롬프트의 마지막 사람의 말에 들어간다.

찾는 글은 이번 라운드의 장면과 플레이어들의 선언이다. 찾는 글을 벡터로 바꿔 판의 항목 벡터들과의 거리를 잰다
(app/lore/indexing.py 가 만들어 둔 것). 그 거리로 두 가지를 고른다.
  1. 키워드: 항목의 이름이나 키워드가 글에 그대로 들어 있고(대소문자 무시), 거리가 keyword_max_distance 이하인 것.
     고유 명사에 강하다. "드워프가"처럼 조사가 붙어도 "드워프"가 들어 있다.
     거리를 보는 것은 동음이의어를 막으려는 것이다. "계획을 망치고"에 키워드 "망치"인 항목이 걸려도, 글 전체의 뜻이
     그 항목과 멀면 넣지 않는다.
  2. 벡터: 거리가 max_distance 이하인 것, 가까운 순으로 limit 개까지. 이름이 나오지 않아도 뜻이 가까운 것을 고른다.
키워드로 고른 것을 먼저, 그다음 가까운 순으로 넣는다. 글자 수의 합이 LORE_MAX_CHARS 를 넘지 않게 한다.

두 거리 기준은 평가 도구(evals/lore, scripts/eval_lore.py)로 잰 값이다. 모델마다 거리의 크기가 달라서,
임베딩 모델을 바꾸면 다시 재서 설정(LORE_MAX_DISTANCE, LORE_KEYWORD_MAX_DISTANCE)을 고친다.

실패해도 서술을 막지 않는다.
  - 임베딩 모델이 실패하면(꺼져 있음) 거리를 모른다. 키워드로만, 거리를 보지 않고 고른다. 이유만 로그에 남긴다.
  - 판의 벡터가 모자라면(게시 직후의 색인이 실패했거나 예전 판) 있는 것으로 찾고, 색인을 다시 맡긴다.
    벡터가 없는 항목은 거리를 모르므로 키워드로 걸리면 그대로 넣는다.

항목의 글은 테이블의 복사본(content)에서 읽는다. AI 의 입력은 복사본에서만 읽기로 했다.
벡터는 판(version_id)마다 있다. 복사본은 판에서 통째로 복사한 것이라 항목의 id 가 같다.
"""

import logging
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.provider import ProviderError
from app.assets.scenarios.snapshot import EntrySnapshot, read_snapshot
from app.lore import repository
from app.lore.texts import version_entries
from app.rounds.narrator import LoreNote, NarrationRequest
from app.tables import repository as table_repository

logger = logging.getLogger(__name__)

# 넣는 항목의 글자 수(이름 + 내용)의 합의 상한. 항목 하나가 600자 안쪽이라 5~6개쯤이다
LORE_MAX_CHARS = 3000
# 벡터로 고르는 항목의 수의 상한
NEAREST_LIMIT = 8
# 이보다 먼(코사인 거리가 큰) 항목은 벡터로 고르지 않는다. 관련 없는 것까지 넣지 않게 한다.
# bge-m3 로 잰 값이다(평가: 맞는 항목은 0.30~0.51, 그 밖의 항목은 중앙 0.61). 설정 LORE_MAX_DISTANCE 의 기본값
MAX_DISTANCE = 0.45
# 키워드로 걸린 항목도 거리가 이보다 멀면 넣지 않는다(동음이의어).
# bge-m3 로 잰 값이다(평가: 맞는 히트는 0.46 까지, 아닌 히트는 중앙 0.55). 설정 LORE_KEYWORD_MAX_DISTANCE 의 기본값
KEYWORD_MAX_DISTANCE = 0.50


@dataclass(frozen=True)
class Thresholds:
    """고르는 규칙의 숫자들. 거리는 코사인 거리다(0 이면 같은 방향, 1 이면 직각)."""

    max_distance: float = MAX_DISTANCE
    keyword_max_distance: float = KEYWORD_MAX_DISTANCE
    limit: int = NEAREST_LIMIT


@dataclass(frozen=True)
class Candidates:
    """고를 수 있는 항목들. 테이블이 어느 판에서 왔는지(벡터를 찾을 곳)와, 복사본의 항목 전부."""

    version_id: uuid.UUID
    entries: list[EntrySnapshot]


class Indexer(Protocol):
    """판의 색인을 맡기는 것. 구현은 app/lore/indexing.py 의 LoreIndexer 다."""

    def schedule(self, version_id: uuid.UUID) -> None: ...


def query_text(request: NarrationRequest) -> str:
    """찾는 글. 이번 장면과, 선언한 사람마다 "이름: 선언" 한 줄씩이다. 선언하지 않은 사람은 뺀다."""
    lines = [request.scene]
    lines.extend(f'{move.character_name}: {move.content}' for move in request.moves if move.content)
    return '\n'.join(lines)


def mentions(entry: EntrySnapshot, text: str) -> bool:
    """항목의 이름이나 키워드 중 하나가 글에 그대로 들어 있는가. 대소문자는 가리지 않는다."""
    folded = text.casefold()
    return any(word.casefold() in folded for word in [entry.name, *entry.keywords] if word.strip())


def keyword_hits(entries: list[EntrySnapshot], text: str) -> list[EntrySnapshot]:
    """이름이나 키워드가 글에 들어 있는 항목들. 항목의 차례대로다."""
    return [entry for entry in entries if mentions(entry, text)]


def note_size(entry: EntrySnapshot) -> int:
    """항목 하나가 차지하는 글자 수(이름 + 내용)."""
    return len(entry.name) + len(entry.content)


def pick(ordered: Sequence[EntrySnapshot], max_chars: int = LORE_MAX_CHARS) -> list[EntrySnapshot]:
    """
    차례대로 넣되 글자 수의 합이 max_chars 를 넘지 않게 고른다. 같은 항목은 한 번만.

    들어가지 않는 항목은 건너뛰고 다음 것을 본다. 뒤의 짧은 항목은 들어갈 수 있다.
    """
    picked: list[EntrySnapshot] = []
    seen: set[uuid.UUID] = set()
    used = 0
    for entry in ordered:
        size = note_size(entry)
        if entry.id in seen or used + size > max_chars:
            continue
        picked.append(entry)
        seen.add(entry.id)
        used += size
    return picked


def nearest_within(
    entries: list[EntrySnapshot], distances: Mapping[uuid.UUID, float], max_distance: float, limit: int
) -> list[EntrySnapshot]:
    """거리가 max_distance 이하인 항목들, 가까운 순으로 limit 개까지. 거리를 모르는 항목은 고르지 않는다."""
    near = [entry for entry in entries if distances.get(entry.id, math.inf) <= max_distance]
    return sorted(near, key=lambda entry: distances[entry.id])[:limit]


def near_enough(entry: EntrySnapshot, distances: Mapping[uuid.UUID, float], max_distance: float) -> bool:
    """키워드로 걸린 항목을 넣어도 되는가. 거리가 max_distance 이하이거나, 거리를 모르면(벡터가 없음) 넣는다."""
    return distances.get(entry.id, -math.inf) <= max_distance


def choose(
    entries: list[EntrySnapshot], text: str, distances: Mapping[uuid.UUID, float], thresholds: Thresholds
) -> list[EntrySnapshot]:
    """
    넣을 항목을 고른다. 키워드로 걸리고 거리가 가까운 것을 먼저, 그다음 뜻이 가까운 것을, 글자 수 안에서.

    distances 는 항목마다 찾는 글과의 거리다. 임베딩이 실패했으면 비어 있고, 그러면 키워드로만 고른다.
    서버와 평가 도구(evals/lore)가 함께 쓴다. 평가한 규칙과 실제로 도는 규칙이 같아야 한다.
    """
    hits = [
        entry for entry in keyword_hits(entries, text) if near_enough(entry, distances, thresholds.keyword_max_distance)
    ]
    return pick([*hits, *nearest_within(entries, distances, thresholds.max_distance, thresholds.limit)])


def to_note(entry: EntrySnapshot) -> LoreNote:
    """고른 항목을 서술자에게 줄 모양으로."""
    return LoreNote(entry_id=entry.id, name=entry.name, content=entry.content)


async def load_candidates(session_factory: async_sessionmaker[AsyncSession], table_id: uuid.UUID) -> Candidates | None:
    """테이블의 판과 복사본의 로어북 항목. 테이블이 없으면 None."""
    async with session_factory() as session:
        table = await table_repository.find_table(session, table_id)
        if table is None:
            return None
        return Candidates(version_id=table.version_id, entries=version_entries(read_snapshot(table.content)))


@dataclass(frozen=True)
class LoreRetriever:
    """
    서술하기 직전에 로어북 항목을 고르는 것. closing.LoreFinder 의 구현이다.

    앱에 하나 둔다(app/main.py). 임베더는 색인과 같은 것을 쓴다. 모델이 다르면 벡터를 견줄 수 없다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    embedder: Embedder
    indexer: Indexer
    thresholds: Thresholds = Thresholds()

    async def find(self, request: NarrationRequest) -> list[LoreNote]:
        """이번 장면에 맞는 항목들. 테이블이 없거나 로어북이 없으면 빈 목록이다."""
        if request.table_id is None:
            return []
        candidates = await load_candidates(self.session_factory, request.table_id)
        if candidates is None or not candidates.entries:
            return []
        text = query_text(request)
        distances = await self.distances(candidates, text)
        return [to_note(entry) for entry in choose(candidates.entries, text, distances, self.thresholds)]

    async def distances(self, candidates: Candidates, text: str) -> dict[uuid.UUID, float]:
        """
        항목마다 찾는 글과의 거리.

        벡터가 모자라면 색인을 다시 맡긴다(없는 것만 만든다). 모델이 실패하면 빈 사전이다(거리를 모른다).
        복사본에 없는 항목의 거리가 섞여 있어도 된다. 고르는 함수(choose)는 복사본의 항목을 기준으로 돈다.
        """
        await self.refill(candidates)
        try:
            (vector,) = await self.embedder.embed([text])
        except ProviderError as error:
            logger.warning('찾는 글을 벡터로 바꾸지 못했다(%s). 키워드로만 고른다', error)
            return {}
        async with self.session_factory() as session:
            return await repository.entry_distances(session, candidates.version_id, self.embedder.model, vector)

    async def refill(self, candidates: Candidates) -> None:
        """판의 벡터가 항목보다 적으면 색인을 맡긴다. 기다리지 않는다."""
        async with self.session_factory() as session:
            count = await repository.count_vectors(session, candidates.version_id, self.embedder.model)
        if count < len(candidates.entries):
            self.indexer.schedule(candidates.version_id)
