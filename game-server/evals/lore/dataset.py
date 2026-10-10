# game-server/evals/lore/dataset.py

"""
평가 데이터(YAML)를 읽고 검사한다.

데이터는 사람이 손으로 늘린다. 실수(없는 항목을 정답으로 적음, 칸을 빠뜨림)를 읽을 때 잡는다.
실수가 있으면 무엇이 틀렸는지 모두 모아 DatasetError 로 알린다. 테스트가 늘 데이터 파일을 읽어 보므로 CI 에서 걸린다.

항목은 서버의 판에 든 항목과 같은 모양(EntrySnapshot)으로, 질의는 서술 요청(NarrationRequest)으로 바꾼다.
그래야 서버의 검색 함수(app/lore/retrieval.py)를 그대로 쓸 수 있다.
항목의 id 는 이름에서 만든다(uuid5). 같은 데이터면 늘 같은 id 다.
"""

import enum
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.assets.scenarios.snapshot import EntrySnapshot
from app.rounds.narrator import Move, NarrationRequest

# 기본 데이터 파일
DEFAULT_PATH = Path(__file__).with_name('chase.yaml')

# 실제 로어북 항목과 같은 제한(app/assets/lorebooks/schemas.py). 평가 데이터도 실제로 만들 수 있는 항목이어야 한다
NAME_MAX = 100
KEYWORDS_MAX = 5
KEYWORD_MAX = 30
CONTENT_MAX = 500

# 항목의 id 를 만드는 이름 공간. 아무 값이나 고정해 두면 된다
ENTRY_NAMESPACE = uuid.UUID('6f1c0b52-6d0e-4c3a-9c55-0d6b0b7a9e11')


class Kind(enum.StrEnum):
    """질의의 종류. 결과를 종류별로 나눠 본다."""

    # 이름이나 키워드가 나온다
    NAME = 'name'
    # 이름 없이 뜻으로만
    MEANING = 'meaning'
    # 낱말은 같지만 뜻이 다르다. 맞는 항목이 없다
    DISTRACTOR = 'distractor'
    # 관련된 항목이 없다
    NONE = 'none'


# 맞는 항목이 없어야 하는 종류
EMPTY_KINDS = frozenset({Kind.DISTRACTOR, Kind.NONE})


class DatasetError(Exception):
    """데이터가 틀렸다. problems 에 틀린 곳이 모두 들어 있다."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__('\n'.join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Query:
    """정답을 붙인 질의 하나."""

    id: str
    set: str
    kind: Kind
    request: NarrationRequest
    expected: frozenset[str]


@dataclass(frozen=True)
class Dataset:
    """시나리오 하나의 항목들과 질의들."""

    title: str
    entries: list[EntrySnapshot]
    queries: list[Query]


def entry_id(name: str) -> uuid.UUID:
    """항목의 id. 이름에서 만든다."""
    return uuid.uuid5(ENTRY_NAMESPACE, name)


def entry_problems(raw: dict[str, Any], index: int) -> list[str]:
    """항목 하나의 틀린 곳들."""
    where = f'entries[{index}]'
    name = raw.get('name')
    if not isinstance(name, str) or not name.strip():
        return [f'{where}: name 이 없다']
    problems = []
    keywords = raw.get('keywords', [])
    content = raw.get('content', '')
    if len(name) > NAME_MAX:
        problems.append(f'{where} {name}: 이름이 {NAME_MAX}자를 넘는다')
    if not isinstance(keywords, list) or len(keywords) > KEYWORDS_MAX:
        problems.append(f'{where} {name}: 키워드는 {KEYWORDS_MAX}개까지의 목록이다')
    elif any(not isinstance(word, str) or not word.strip() or len(word) > KEYWORD_MAX for word in keywords):
        problems.append(f'{where} {name}: 키워드는 빈 글이 아니고 {KEYWORD_MAX}자까지다')
    if not isinstance(content, str) or len(content) > CONTENT_MAX:
        problems.append(f'{where} {name}: 내용은 {CONTENT_MAX}자까지의 글이다')
    return problems


def query_problems(raw: dict[str, Any], index: int, names: set[str]) -> list[str]:
    """질의 하나의 틀린 곳들. names 는 항목 이름 전부다."""
    where = f'queries[{index}] {raw.get("id", "")}'.rstrip()
    problems = []
    for field in ('id', 'set', 'kind', 'scene'):
        if not isinstance(raw.get(field), str):
            problems.append(f'{where}: {field} 가 없다')
    # kind 가 틀리면 정답이 비어야 하는지 따질 수 없다. None 으로 두고 그 검사를 건너뛴다
    kind = raw.get('kind') if raw.get('kind') in list(Kind) else None
    if kind is None:
        problems.append(f'{where}: kind 는 {", ".join(Kind)} 중 하나다')
    moves = raw.get('moves', [])
    if not isinstance(moves, list) or any(
        not isinstance(move, dict) or not isinstance(move.get('character'), str) for move in moves
    ):
        problems.append(f'{where}: moves 는 character 와 content 의 목록이다')
    expected = raw.get('expected')
    if not isinstance(expected, list):
        return [*problems, f'{where}: expected 가 목록이 아니다']
    unknown = [name for name in expected if name not in names]
    if unknown:
        problems.append(f'{where}: 없는 항목을 정답으로 적었다({", ".join(map(str, unknown))})')
    if kind in EMPTY_KINDS and expected:
        problems.append(f'{where}: {kind} 질의는 정답이 비어 있어야 한다')
    if kind is not None and kind not in EMPTY_KINDS and not expected:
        problems.append(f'{where}: 정답이 없다. 맞는 항목이 없으면 kind 를 none 으로')
    return problems


def duplicates(values: list[str]) -> list[str]:
    """두 번 이상 나온 값들. 처음 나온 차례대로."""
    seen: set[str] = set()
    repeated: list[str] = []
    for value in values:
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return repeated


def find_problems(document: Any) -> list[str]:
    """문서 전체의 틀린 곳들. 없으면 빈 목록이다."""
    if not isinstance(document, dict):
        return ['문서는 title, entries, queries 를 가진 사전이다']
    entries = document.get('entries') or []
    queries = document.get('queries') or []
    if not isinstance(entries, list) or not isinstance(queries, list):
        return ['entries 와 queries 는 목록이다']
    if not all(isinstance(raw, dict) for raw in [*entries, *queries]):
        return ['entries 와 queries 의 칸은 하나하나가 사전이다']
    problems = [problem for index, raw in enumerate(entries) for problem in entry_problems(raw, index)]
    names = [raw.get('name') for raw in entries if isinstance(raw.get('name'), str)]
    problems += [f'항목 이름이 겹친다: {name}' for name in duplicates(names)]
    problems += [problem for index, raw in enumerate(queries) for problem in query_problems(raw, index, set(names))]
    ids = [raw.get('id') for raw in queries if isinstance(raw.get('id'), str)]
    problems += [f'질의 id 가 겹친다: {query_id}' for query_id in duplicates(ids)]
    return problems


def to_entry(raw: dict[str, Any]) -> EntrySnapshot:
    """항목 하나를 판의 항목 모양으로."""
    return EntrySnapshot(
        id=entry_id(raw['name']), name=raw['name'], keywords=raw.get('keywords', []), content=raw.get('content', '')
    )


def to_query(raw: dict[str, Any]) -> Query:
    """질의 하나를 서술 요청이 든 질의로. 라운드 번호는 의미가 없어 1 로 둔다."""
    moves = [Move(move['character'], move.get('content')) for move in raw.get('moves', [])]
    request = NarrationRequest(round_number=1, scene=raw['scene'], moves=moves)
    return Query(raw['id'], raw['set'], Kind(raw['kind']), request, frozenset(raw['expected']))


def parse_dataset(document: Any) -> Dataset:
    """읽은 문서를 데이터로 바꾼다. 틀린 곳이 있으면 DatasetError."""
    problems = find_problems(document)
    if problems:
        raise DatasetError(problems)
    return Dataset(
        title=str(document.get('title', '')),
        entries=[to_entry(raw) for raw in document['entries']],
        queries=[to_query(raw) for raw in document['queries']],
    )


def load_dataset(path: Path = DEFAULT_PATH) -> Dataset:
    """파일을 읽어 데이터로 바꾼다. 틀린 곳이 있으면 DatasetError."""
    return parse_dataset(yaml.safe_load(path.read_text(encoding='utf-8')))


def only_set(dataset: Dataset, name: str | None) -> Dataset:
    """이 묶음(set)의 질의만 남긴다. name 이 None 이면 그대로다."""
    if name is None:
        return dataset
    return Dataset(dataset.title, dataset.entries, [query for query in dataset.queries if query.set == name])
