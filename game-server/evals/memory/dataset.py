# game-server/evals/memory/dataset.py

"""
지난 일 검색의 평가 데이터(YAML)를 읽고 검사한다.

데이터는 게임 하나의 기록이다. 라운드마다 장면(그 라운드를 여는 GM 의 서술)과 플레이어들이 한 말을 적는다.
기억은 서버와 같은 함수로 만든다(app/memory/texts.py). 라운드 N 의 기억 = N 에 한 말 + N+1 의 장면.
질의는 서술하는 라운드의 번호, 그 라운드의 장면과 선언, 그리고 넣고 싶은 기억(라운드 번호)이다.

정답은 그 라운드에서 고를 수 있는 기억(지난 기록보다 앞, app/memory/retrieval.py 의 eligible)이어야 한다.
고를 수 없는 라운드를 정답으로 적으면 읽을 때 잡는다.

질의의 종류와 점수의 틀은 로어북 평가의 것을 그대로 쓴다(evals/lore). 정답은 라운드 번호를 글자로 바꿔 담는다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.assets.models import LoreKind
from app.assets.scenarios.snapshot import EntrySnapshot
from app.memory.retrieval import eligible
from app.memory.texts import Memory, memories_of
from app.rounds.narrator import Move, NarrationRequest, PastRound
from evals.lore.dataset import EMPTY_KINDS, DatasetError, Kind, Query, duplicates, entry_id

# 기본 데이터 파일
DEFAULT_PATH = Path(__file__).with_name('chase_log.yaml')


@dataclass(frozen=True)
class MemoryDataset:
    """게임 하나의 인물들, 라운드들로 만든 기억들, 질의들."""

    title: str
    people: list[EntrySnapshot]
    memories: list[Memory]
    queries: list[Query]


def round_problems(rounds: list[Any]) -> list[str]:
    """라운드들의 틀린 곳들. 번호는 1 부터 빠짐없이, 장면은 글, 한 말은 글의 목록이다."""
    problems = []
    for index, raw in enumerate(rounds, start=1):
        if not isinstance(raw, dict):
            problems.append(f'rounds[{index - 1}]: 사전이 아니다')
            continue
        if raw.get('number') != index:
            problems.append(f'rounds[{index - 1}]: number 는 {index} 여야 한다(1 부터 빠짐없이)')
        if not isinstance(raw.get('scene'), str) or not raw['scene'].strip():
            problems.append(f'rounds[{index - 1}]: scene 이 없다')
        lines = raw.get('lines', [])
        if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
            problems.append(f'rounds[{index - 1}]: lines 는 글의 목록이다')
    return problems


def person_problems(people: list[Any]) -> list[str]:
    """인물들의 틀린 곳들. 이름이 있고 겹치지 않으며, 키워드는 글의 목록이다."""
    problems = []
    for index, raw in enumerate(people):
        if not isinstance(raw, dict) or not isinstance(raw.get('name'), str):
            problems.append(f'people[{index}]: name 이 없다')
            continue
        keywords = raw.get('keywords', [])
        if not isinstance(keywords, list) or any(not isinstance(word, str) for word in keywords):
            problems.append(f'people[{index}] {raw["name"]}: keywords 는 글의 목록이다')
    names = [raw['name'] for raw in people if isinstance(raw, dict) and isinstance(raw.get('name'), str)]
    problems += [f'인물 이름이 겹친다: {name}' for name in duplicates(names)]
    return problems


def query_problems(raw: Any, index: int, last_round: int) -> list[str]:
    """
    질의 하나의 틀린 곳들. last_round 는 데이터의 마지막 라운드 번호다.

    정답은 서술하는 라운드(round)에서 고를 수 있는 기억이어야 한다. 기억이 되려면 다음 라운드가 있어야 한다.
    """
    if not isinstance(raw, dict):
        return [f'queries[{index}]: 사전이 아니다']
    where = f'queries[{index}] {raw.get("id", "")}'.rstrip()
    problems = []
    for field in ('id', 'kind', 'scene'):
        if not isinstance(raw.get(field), str):
            problems.append(f'{where}: {field} 가 없다')
    kind = raw.get('kind') if raw.get('kind') in list(Kind) else None
    if kind is None:
        problems.append(f'{where}: kind 는 {", ".join(Kind)} 중 하나다')
    current = raw.get('round')
    if not isinstance(current, int) or not 1 <= current <= last_round + 1:
        return [*problems, f'{where}: round 는 1 부터 {last_round + 1} 까지의 번호다']
    moves = raw.get('moves', [])
    if not isinstance(moves, list) or any(
        not isinstance(move, dict) or not isinstance(move.get('character'), str) for move in moves
    ):
        problems.append(f'{where}: moves 는 character 와 content 의 목록이다')
    expected = raw.get('expected')
    if not isinstance(expected, list) or any(not isinstance(number, int) for number in expected):
        return [*problems, f'{where}: expected 는 라운드 번호의 목록이다']
    choosable = {memory.number for memory in eligible(fake_memories(last_round), current)}
    wrong = [number for number in expected if number not in choosable]
    if wrong:
        problems.append(
            f'{where}: {current} 라운드에서 고를 수 없는 기억을 정답으로 적었다({", ".join(map(str, wrong))})'
        )
    if kind in EMPTY_KINDS and expected:
        problems.append(f'{where}: {kind} 질의는 정답이 비어 있어야 한다')
    if kind is not None and kind not in EMPTY_KINDS and not expected:
        problems.append(f'{where}: 정답이 없다. 맞는 기억이 없으면 kind 를 none 으로')
    return problems


def fake_memories(last_round: int) -> list[Memory]:
    """라운드가 last_round 개인 게임의 기억들의 번호만 맞춘 것. 정답을 검사할 때 쓴다."""
    return memories_of([PastRound(number=number, scene='') for number in range(1, last_round + 1)])


def find_problems(document: Any) -> list[str]:
    """문서 전체의 틀린 곳들. 없으면 빈 목록이다."""
    if not isinstance(document, dict):
        return ['문서는 title, people, rounds, queries 를 가진 사전이다']
    people = document.get('people') or []
    rounds = document.get('rounds') or []
    queries = document.get('queries') or []
    if not all(isinstance(value, list) for value in (people, rounds, queries)):
        return ['people, rounds, queries 는 목록이다']
    problems = person_problems(people) + round_problems(rounds)
    problems += [problem for index, raw in enumerate(queries) for problem in query_problems(raw, index, len(rounds))]
    ids = [raw.get('id') for raw in queries if isinstance(raw, dict) and isinstance(raw.get('id'), str)]
    problems += [f'질의 id 가 겹친다: {query_id}' for query_id in duplicates(ids)]
    return problems


def to_person(raw: dict[str, Any]) -> EntrySnapshot:
    """인물 하나를 로어북의 인물 항목 모양으로."""
    return EntrySnapshot(
        id=entry_id(raw['name']), name=raw['name'], keywords=raw.get('keywords', []), content='', kind=LoreKind.PERSON
    )


def to_past(raw: dict[str, Any]) -> PastRound:
    """라운드 하나를 지난 라운드의 모양으로."""
    return PastRound(number=raw['number'], scene=raw['scene'], lines=list(raw.get('lines', [])))


def to_query(raw: dict[str, Any]) -> Query:
    """질의 하나를 서술 요청이 든 질의로. 정답은 라운드 번호를 글자로 바꿔 담는다."""
    moves = [Move(move['character'], move.get('content')) for move in raw.get('moves', [])]
    request = NarrationRequest(round_number=raw['round'], scene=raw['scene'], moves=moves)
    return Query(raw['id'], 'v1', Kind(raw['kind']), request, frozenset(str(number) for number in raw['expected']))


def parse_dataset(document: Any) -> MemoryDataset:
    """읽은 문서를 데이터로 바꾼다. 틀린 곳이 있으면 DatasetError."""
    problems = find_problems(document)
    if problems:
        raise DatasetError(problems)
    return MemoryDataset(
        title=str(document.get('title', '')),
        people=[to_person(raw) for raw in document.get('people') or []],
        memories=memories_of([to_past(raw) for raw in document['rounds']]),
        queries=[to_query(raw) for raw in document['queries']],
    )


def load_dataset(path: Path = DEFAULT_PATH) -> MemoryDataset:
    """파일을 읽어 데이터로 바꾼다. 틀린 곳이 있으면 DatasetError."""
    return parse_dataset(yaml.safe_load(path.read_text(encoding='utf-8')))
