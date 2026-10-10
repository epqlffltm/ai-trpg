# game-server/app/memory/history.py

"""
이번 장면에 나온 인물의 이력을 모은다. 지난 서술에서 그 인물이 나온 문장을 라운드 순서로 골라낸다(#107 ②).

지난 일(app/memory/retrieval.py)은 라운드를 통째로 몇 개 고른다. 인물이 여러 라운드에 나오면 그중 둘만 들어간다.
이력은 인물 하나의 일을 라운드마다 한두 문장씩 모은다. 순서대로 놓여 우호였다가 배신한 것 같은 바뀐 태도가 보인다.

AI 를 부르지 않는다. 임베딩 모델은 글을 쓰지 못해 요약할 수 없고, 생성 모델의 요약은 틀리면 틀린 채로 쌓인다.
골라낸 문장은 플레이어가 이미 본 서술 그대로라 지어낸 것이 없다.
대신 이름이나 키워드가 없는 문장("그녀가 웃었다", "동맹은 깨졌다")은 놓친다. 얼마나 놓치는지는 평가 도구가 잰다
(scripts/eval_memory.py). 많이 놓치면 생성 모델의 요약을 더한다(#107 ③).

누구의 이력을 모으나: 로어북 검색이 이번 장면에 고른 인물 항목들이다(request.lore).
로어북 검색은 키워드로 걸린 항목도 거리가 멀면 뺀다("종이로 접은 부채"의 악역영애). 그 판단을 따른다.
이름표도 로어북 검색이 정한 것이다.

어느 서술에서 모으나: 지난 기록(최근 3 라운드)보다 앞의 라운드를 연 서술이다. 지난 기록에 든 서술은 이미 대화에 있다.
1 라운드의 장면은 시나리오의 도입부라 지난 일이 아니다.
플레이어들이 한 말(선언)은 모으지 않는다. 일어난 일은 서술에 있다.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assets.models import LoreKind
from app.assets.scenarios.snapshot import EntrySnapshot, read_snapshot
from app.lore.retrieval import mentions
from app.lore.texts import version_entries
from app.memory import repository
from app.rounds.narration_request import to_past
from app.rounds.narrator import HistoryLine, NarrationRequest, PastRound, PersonHistory
from app.rounds.prompt import HISTORY_ROUNDS
from app.tables import repository as table_repository

# 인물 하나에 넣는 문장의 수와 글자 수의 상한. 최근 것부터 채운다
HISTORY_LINES = 5
PERSON_MAX_CHARS = 600
# 이력을 모으는 인물의 수. 로어북 검색이 고른 차례대로다
HISTORY_PEOPLE = 3
# 문장 하나. 마침표·느낌표·물음표·말줄임표(와 그 뒤의 닫는 따옴표)까지, 또는 줄의 끝까지
SENTENCE = re.compile(r'[^.!?…\n]+(?:[.!?…]+["\'”’」』)]*|$)', re.MULTILINE)


def sentences(text: str) -> list[str]:
    """글을 문장으로 나눈다. 앞뒤 빈칸을 떼고 빈 문장은 뺀다."""
    return [piece.strip() for piece in SENTENCE.findall(text) if piece.strip()]


def scene_lines(rounds: Sequence[PastRound], current: int, recent: int = HISTORY_ROUNDS) -> list[HistoryLine]:
    """
    모을 수 있는 서술의 문장들. 라운드 순서다.

    current 는 서술하는 라운드의 번호다. 지난 기록은 current - recent 라운드부터라 그 앞의 장면만 본다.
    1 라운드의 장면(도입부)은 뺀다.
    """
    return [
        HistoryLine(past.number, sentence)
        for past in sorted(rounds, key=lambda past: past.number)
        if 1 < past.number < current - recent
        for sentence in sentences(past.scene)
    ]


def lines_about(person: EntrySnapshot, lines: Sequence[HistoryLine]) -> list[HistoryLine]:
    """인물의 이름이나 키워드가 든 문장들. 차례는 그대로다."""
    return [line for line in lines if mentions(person, line.text)]


def latest(lines: Sequence[HistoryLine], count: int, max_chars: int) -> list[HistoryLine]:
    """
    최근 문장부터 count 개와 글자 수 max_chars 안에서 고른다. 고른 것은 라운드 순서로 돌려준다.

    최근 일이 지금의 태도에 가깝다. 들어가지 않는 긴 문장은 건너뛰고 그 앞의 것을 본다.
    """
    picked: list[HistoryLine] = []
    used = 0
    for line in reversed(lines):
        if len(picked) == count:
            break
        if used + len(line.text) > max_chars:
            continue
        picked.append(line)
        used += len(line.text)
    return list(reversed(picked))


def history_of(person: EntrySnapshot, lines: Sequence[HistoryLine]) -> list[HistoryLine]:
    """인물 하나의 이력. 그 인물이 나온 문장 중 최근 것들, 라운드 순서다."""
    return latest(lines_about(person, lines), HISTORY_LINES, PERSON_MAX_CHARS)


@dataclass(frozen=True)
class Sources:
    """이력의 재료. 복사본의 인물 항목(id 에서 항목으로)과 테이블의 라운드들(이번 라운드까지)."""

    people: dict[uuid.UUID, EntrySnapshot]
    rounds: list[PastRound]


async def load_sources(
    session_factory: async_sessionmaker[AsyncSession], table_id: uuid.UUID, current: int
) -> Sources | None:
    """복사본의 인물 항목들과 이번 라운드까지의 라운드들. 테이블이 없으면 None."""
    async with session_factory() as session:
        table = await table_repository.find_table(session, table_id)
        if table is None:
            return None
        entries = version_entries(read_snapshot(table.content))
        rounds = [to_past(round_) for round_ in await repository.list_rounds_until(session, table_id, current)]
    people = {entry.id: entry for entry in entries if entry.kind == LoreKind.PERSON}
    return Sources(people=people, rounds=rounds)


@dataclass(frozen=True)
class HistoryCollector:
    """
    서술하기 직전에 인물의 이력을 모으는 것. closing.HistoryFinder 의 구현이다. 앱에 하나 둔다(app/main.py).

    로어북 검색이 끝난 요청을 받는다(request.lore 에 고른 항목이 있어야 한다).
    """

    session_factory: async_sessionmaker[AsyncSession]

    async def find(self, request: NarrationRequest) -> list[PersonHistory]:
        """
        로어북이 고른 인물들의 이력. 이력이 빈 인물은 뺀다.

        테이블이 없거나, 고른 인물이 없으면 DB 를 읽지 않고 빈 목록이다.
        """
        notes = [note for note in request.lore if note.kind == LoreKind.PERSON][:HISTORY_PEOPLE]
        if request.table_id is None or not notes:
            return []
        sources = await load_sources(self.session_factory, request.table_id, request.round_number)
        if sources is None:
            return []
        lines = scene_lines(sources.rounds, request.round_number)
        histories = [
            PersonHistory(note.entry_id, note.name, history_of(sources.people[note.entry_id], lines))
            for note in notes
            if note.entry_id in sources.people
        ]
        return [history for history in histories if history.lines]
