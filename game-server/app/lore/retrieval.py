# game-server/app/lore/retrieval.py

"""
서술하기 직전에 이번 장면에 맞는 로어북 항목을 고른다(검색). 고른 항목은 프롬프트의 마지막 사람의 말에 들어간다.

찾는 글은 이번 라운드의 장면과 플레이어들의 선언이다. 두 가지로 찾아 합친다.
  1. 키워드: 항목의 이름이나 키워드가 글에 그대로 들어 있으면 고른다(대소문자 무시). 고유 명사에 강하다.
     "드워프가"처럼 조사가 붙어도 "드워프"가 들어 있다.
  2. 벡터: 찾는 글을 벡터로 바꿔 판의 항목 벡터와 견준다(app/lore/indexing.py 가 만들어 둔 것). 뜻이 가까운 것을 고른다.
키워드로 고른 것을 먼저, 그다음 가까운 순으로 넣는다. 글자 수의 합이 LORE_MAX_CHARS 를 넘지 않게 한다.

실패해도 서술을 막지 않는다.
  - 임베딩 모델이 실패하면(꺼져 있음) 키워드로만 고른다. 이유만 로그에 남긴다.
  - 판의 벡터가 모자라면(게시 직후의 색인이 실패했거나 예전 판) 있는 것으로 찾고, 색인을 다시 맡긴다.

항목의 글은 테이블의 복사본(content)에서 읽는다. AI 의 입력은 복사본에서만 읽기로 했다.
벡터는 판(version_id)마다 있다. 복사본은 판에서 통째로 복사한 것이라 항목의 id 가 같다.
"""

import logging
import uuid
from collections.abc import Sequence
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
# 임시 값이다. 평가 도구(#93 ③)로 실제 모델의 거리를 재서 정한다
MAX_DISTANCE = 0.6


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


def choose(entries: list[EntrySnapshot], text: str, nearest: list[EntrySnapshot]) -> list[EntrySnapshot]:
    """
    넣을 항목을 고른다. 이름이나 키워드가 나온 것을 먼저, 그다음 nearest(가까운 순)를, 글자 수 안에서.

    서버와 평가 도구(evals/lore)가 함께 쓴다. 평가한 규칙과 실제로 도는 규칙이 같아야 한다.
    """
    return pick([*keyword_hits(entries, text), *nearest])


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

    async def find(self, request: NarrationRequest) -> list[LoreNote]:
        """이번 장면에 맞는 항목들. 테이블이 없거나 로어북이 없으면 빈 목록이다."""
        if request.table_id is None:
            return []
        candidates = await load_candidates(self.session_factory, request.table_id)
        if candidates is None or not candidates.entries:
            return []
        text = query_text(request)
        nearest = await self.nearest(candidates, text)
        return [to_note(entry) for entry in choose(candidates.entries, text, nearest)]

    async def nearest(self, candidates: Candidates, text: str) -> list[EntrySnapshot]:
        """
        찾는 글과 뜻이 가까운 항목들. 가까운 것부터다.

        벡터가 모자라면 색인을 다시 맡긴다(없는 것만 만든다). 모델이 실패하면 빈 목록이다.
        복사본에 없는 항목의 벡터는 버린다.
        """
        await self.refill(candidates)
        try:
            (vector,) = await self.embedder.embed([text])
        except ProviderError as error:
            logger.warning('찾는 글을 벡터로 바꾸지 못했다(%s). 키워드로만 고른다', error)
            return []
        async with self.session_factory() as session:
            ids = await repository.nearest_entry_ids(
                session, candidates.version_id, self.embedder.model, vector, NEAREST_LIMIT, MAX_DISTANCE
            )
        by_id = {entry.id: entry for entry in candidates.entries}
        return [by_id[entry_id] for entry_id in ids if entry_id in by_id]

    async def refill(self, candidates: Candidates) -> None:
        """판의 벡터가 항목보다 적으면 색인을 맡긴다. 기다리지 않는다."""
        async with self.session_factory() as session:
            count = await repository.count_vectors(session, candidates.version_id, self.embedder.model)
        if count < len(candidates.entries):
            self.indexer.schedule(candidates.version_id)
