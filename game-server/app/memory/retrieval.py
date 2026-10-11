# game-server/app/memory/retrieval.py

"""
서술하기 직전에 이번 장면에 맞는 지난 일(기억)을 고른다. 고른 기억은 프롬프트의 마지막 사람의 말에 들어간다.

서술자는 최근 3 라운드를 지난 기록(대화)으로 받는다(app/rounds/prompt.py). 그보다 앞의 라운드는 사라진다.
여기서는 그 앞의 라운드 중 이번 장면에 맞는 것을 몇 개 골라 넣는다.

고르는 규칙(로어북 검색과 같은 틀이다, app/lore/retrieval.py).
  1. 인물: 이번 장면이나 선언에 나온 인물(로어북의 인물 항목. 이름이나 키워드가 그대로 들어 있는 것)이
     나온 기억. 최근 것부터. 같은 인물의 일이 여럿이면 최근 일이 지금의 태도에 가깝다(우호였다가 배신한 NPC).
     거리가 keyword_max_distance 보다 멀면 넣지 않는다. 임베딩이 실패해 거리를 모르면 넣는다.
  2. 벡터: 찾는 글(이번 장면 + 선언)과의 거리가 max_distance 이하인 것, 가까운 순.
인물로 고른 것을 먼저, 그다음 가까운 순으로, count 개와 글자 수 max_chars 안에서 넣는다.
기억 하나의 글은 NOTE_MAX_CHARS 자 안에 넣는다. 한 말이 길어도 결과의 자리를 먼저 남기고,
판정이 있던 줄에는 성공과 실패를 붙인다(app/memory/texts.py 의 note_text).

지난 기록에 이미 들어 있는 라운드(최근 3 라운드)는 고르지 않는다. 같은 일을 두 번 넣지 않는다.

거리 기준은 평가 도구(evals/memory, scripts/eval_memory.py)로 잰다. 기억은 로어북 항목보다 글이 길어
거리의 크기가 다르다. 그래서 로어북과 따로 둔다(MEMORY_MAX_DISTANCE, MEMORY_KEYWORD_MAX_DISTANCE).

실패해도 서술을 막지 않는다.
  - 임베딩 모델이 실패하면 거리를 모른다. 인물로만, 거리를 보지 않고 고른다. 이유만 로그에 남긴다.
  - 벡터가 모자라면(방금 닫힌 라운드, 지난 색인의 실패) 있는 것으로 찾고, 색인을 맡긴다(app/memory/indexing.py).
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
from app.assets.models import LoreKind
from app.assets.scenarios.snapshot import EntrySnapshot, read_snapshot
from app.lore.retrieval import mentions, query_text
from app.lore.texts import version_entries
from app.memory import repository, texts
from app.memory.texts import Memory, memories_of, memory_text
from app.rounds.narration_request import to_past
from app.rounds.narrator import MemoryNote, NarrationRequest
from app.rounds.prompt import HISTORY_ROUNDS
from app.tables import repository as table_repository

logger = logging.getLogger(__name__)

# 넣는 기억의 수와 글자 수의 상한
MEMORY_COUNT = 2
MEMORY_MAX_CHARS = 2000
# 기억 하나의 글자 수의 상한. 넘으면 문장 끝에서 자른다
NOTE_MAX_CHARS = 1000
# 그중 한 말(선언들)이 쓰는 글자 수의 상한. 결과가 길 때 한 말은 여기까지만 쓰고, 나머지는 결과의 자리다.
# 선언 하나가 1,000자까지라(DECLARATION_MAX_LENGTH) 나누지 않으면 한 말만으로 상한이 차서 결과가 통째로 잘린다.
# 결과가 짧으면 남는 자리는 한 말이 쓴다. 숫자는 시작값이다. 실제 모델의 서술로 재서 고친다(scripts/try_memory.py)
NOTE_LINES_MAX_CHARS = 400
# 이보다 먼 기억은 뜻으로 고르지 않는다. bge-m3 로 잰 값이다(평가: 정답인 기억은 중앙 0.40·75% 0.44,
# 그 밖의 기억은 25% 0.49·중앙 0.54. 0.45 면 관련 없는 장면에도 지난 일을 채웠다). 설정 MEMORY_MAX_DISTANCE 의 기본값
MAX_DISTANCE = 0.40
# 인물로 걸린 기억도 이보다 멀면 넣지 않는다(인물의 키워드가 다른 뜻으로 나온 글). bge-m3 로 잰 값이다.
# 0.45 가 점수는 조금 높았지만 이름이 나온 장면의 기억을 놓쳤다. 한 칸 넓혔다.
# 설정 MEMORY_KEYWORD_MAX_DISTANCE 의 기본값
KEYWORD_MAX_DISTANCE = 0.50


@dataclass(frozen=True)
class MemoryThresholds:
    """고르는 규칙의 숫자들. 거리는 코사인 거리다."""

    max_distance: float = MAX_DISTANCE
    keyword_max_distance: float = KEYWORD_MAX_DISTANCE
    count: int = MEMORY_COUNT
    max_chars: int = MEMORY_MAX_CHARS


@dataclass(frozen=True)
class Past:
    """고를 수 있는 것들. 테이블의 기억 전부(이번 라운드 앞)와, 복사본의 인물 항목."""

    memories: list[Memory]
    people: list[EntrySnapshot]


class Indexer(Protocol):
    """테이블의 색인을 맡기는 것. 구현은 app/memory/indexing.py 의 MemoryIndexer 다."""

    def schedule(self, table_id: uuid.UUID) -> None: ...


def eligible(memories: Sequence[Memory], current: int, recent: int = HISTORY_ROUNDS) -> list[Memory]:
    """
    고를 수 있는 기억들. 지난 기록에 들어가는 최근 recent 라운드보다 앞의 것이다.

    current 는 서술하는 라운드의 번호다. 지난 기록은 current - recent 부터 current - 1 까지다.
    """
    return [memory for memory in memories if memory.number < current - recent]


def people_in(entries: Sequence[EntrySnapshot], text: str) -> list[EntrySnapshot]:
    """인물 항목 중 이름이나 키워드가 글에 나온 것들."""
    return [entry for entry in entries if entry.kind == LoreKind.PERSON and mentions(entry, text)]


def about_people(memories: Sequence[Memory], people: Sequence[EntrySnapshot]) -> list[Memory]:
    """이 인물들 중 누구라도 나온 기억들. 최근 것부터다."""
    hits = [memory for memory in memories if any(mentions(person, memory_text(memory)) for person in people)]
    return sorted(hits, key=lambda memory: memory.number, reverse=True)


def near_enough(memory: Memory, distances: Mapping[int, float], max_distance: float) -> bool:
    """인물로 걸린 기억을 넣어도 되는가. 거리가 max_distance 이하이거나, 거리를 모르면(벡터가 없음) 넣는다."""
    return distances.get(memory.number, -math.inf) <= max_distance


def nearest_within(memories: Sequence[Memory], distances: Mapping[int, float], max_distance: float) -> list[Memory]:
    """거리가 max_distance 이하인 기억들, 가까운 순. 거리를 모르는 기억은 고르지 않는다."""
    near = [memory for memory in memories if distances.get(memory.number, math.inf) <= max_distance]
    return sorted(near, key=lambda memory: distances[memory.number])


def note_text(memory: Memory) -> str:
    """기억을 프롬프트에 넣을 글. NOTE_MAX_CHARS 자 안에서 결과를 지키며 자른다(app/memory/texts.py)."""
    return texts.note_text(memory, NOTE_MAX_CHARS, NOTE_LINES_MAX_CHARS)


def pick(ordered: Sequence[Memory], count: int, max_chars: int) -> list[Memory]:
    """
    차례대로 넣되 count 개와 글자 수 max_chars 를 넘지 않게 고른다. 같은 기억은 한 번만.

    들어가지 않는 기억은 건너뛰고 다음 것을 본다.
    """
    picked: list[Memory] = []
    used = 0
    for memory in ordered:
        size = len(note_text(memory))
        if len(picked) == count:
            break
        if memory in picked or used + size > max_chars:
            continue
        picked.append(memory)
        used += size
    return picked


def choose_memories(
    memories: Sequence[Memory],
    people: Sequence[EntrySnapshot],
    distances: Mapping[int, float],
    thresholds: MemoryThresholds,
) -> list[Memory]:
    """
    넣을 기억을 고른다. 장면에 나온 인물이 나온 것(최근 것부터)을 먼저, 그다음 뜻이 가까운 것을.

    memories 는 고를 수 있는 기억들이다(eligible). people 은 장면에 나온 인물 항목들이다(people_in).
    distances 는 기억마다 찾는 글과의 거리다. 임베딩이 실패했으면 비어 있고, 그러면 인물로만 고른다.
    서버와 평가 도구(evals/memory)가 함께 쓴다.
    """
    hits = [
        memory
        for memory in about_people(memories, people)
        if near_enough(memory, distances, thresholds.keyword_max_distance)
    ]
    nearest = nearest_within(memories, distances, thresholds.max_distance)
    return pick([*hits, *nearest], thresholds.count, thresholds.max_chars)


def to_note(memory: Memory) -> MemoryNote:
    """고른 기억을 서술자에게 줄 모양으로."""
    return MemoryNote(round_number=memory.number, text=note_text(memory))


async def load_past(
    session_factory: async_sessionmaker[AsyncSession], table_id: uuid.UUID, current: int
) -> Past | None:
    """테이블의 기억(이번 라운드 앞의 것)과 복사본의 인물 항목. 테이블이 없으면 None."""
    async with session_factory() as session:
        table = await table_repository.find_table(session, table_id)
        if table is None:
            return None
        entries = version_entries(read_snapshot(table.content))
        rounds = [to_past(round_) for round_ in await repository.list_rounds_until(session, table_id, current)]
    people = [entry for entry in entries if entry.kind == LoreKind.PERSON]
    return Past(memories=memories_of(rounds), people=people)


@dataclass(frozen=True)
class MemoryRetriever:
    """
    서술하기 직전에 지난 일을 고르는 것. closing.MemoryFinder 의 구현이다.

    앱에 하나 둔다(app/main.py). 임베더는 색인과 같은 것을 쓴다. 모델이 다르면 벡터를 견줄 수 없다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    embedder: Embedder
    indexer: Indexer
    thresholds: MemoryThresholds = MemoryThresholds()

    async def find(self, request: NarrationRequest) -> list[MemoryNote]:
        """이번 장면에 맞는 지난 일들. 테이블이 없거나 고를 수 있는 기억이 없으면 빈 목록이다."""
        if request.table_id is None:
            return []
        past = await load_past(self.session_factory, request.table_id, request.round_number)
        if past is None:
            return []
        await self.refill(request.table_id, past.memories)
        candidates = eligible(past.memories, request.round_number)
        if not candidates:
            return []
        text = query_text(request)
        distances = await self.distances(request.table_id, text)
        chosen = choose_memories(candidates, people_in(past.people, text), distances, self.thresholds)
        return [to_note(memory) for memory in chosen]

    async def distances(self, table_id: uuid.UUID, text: str) -> dict[int, float]:
        """기억마다 찾는 글과의 거리. 모델이 실패하면 빈 사전이다(거리를 모른다)."""
        try:
            (vector,) = await self.embedder.embed([text])
        except ProviderError as error:
            logger.warning('찾는 글을 벡터로 바꾸지 못했다(%s). 지난 일은 인물로만 고른다', error)
            return {}
        async with self.session_factory() as session:
            return await repository.memory_distances(session, table_id, self.embedder.model, vector)

    async def refill(self, table_id: uuid.UUID, memories: Sequence[Memory]) -> None:
        """테이블의 벡터가 기억보다 적으면 색인을 맡긴다. 기다리지 않는다."""
        async with self.session_factory() as session:
            count = await repository.count_vectors(session, table_id, self.embedder.model)
        if count < len(memories):
            self.indexer.schedule(table_id)
