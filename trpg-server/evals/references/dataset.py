# trpg-server/evals/references/dataset.py

"""
참고 자료 평가의 데이터(YAML)를 읽고 검사한다.

장면은 사람이 손으로 늘린다. 실수(자료에 없는 key, 칸을 빠뜨림, none 인데 정답이 있음)를 읽을 때 모두 모아 알린다.
장면은 두 모양이다(SceneShape). 게임 서버의 라운드와, 대화 서버(chat, story)의 말들이다.
찾는 글(query)은 서버가 만드는 것과 같은 함수로 만든다. 고르는 것은 같다(reference_core 의 find_references).
라운드는 서술 요청(NarrationRequest)으로도 바꾼다. 서술 평가(evals/references/narration.py)가 그것을 쓴다.
자료의 줄은 공용 패키지에 실린 데이터 파일들(reference_core/data.py 의 DATA_FILES: SRD 5.1, 위키백과)을 읽은 것이다.
DB 에 넣은 것과 같다(관리 명령의 load 가 같은 파일을 넣는다). 한국어 이름과 글, 자료(source)도 함께 옮긴다.
생김새 글(look_ko)도 옮긴다. 서버가 벡터로 바꿀 글이 이름과 생김새 글이다(reference_core/texts.py).
"""

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml
from conversation_core.lorebook import query_text as talk_query
from reference_core.data import DATA_FILES
from reference_core.records import ReferenceRecord, StoredReference, read_document

from app.lore.retrieval import query_text as round_query
from app.rounds.narrator import Move, NarrationRequest, StoryContext

# 기본 장면 파일과 자료 파일들
DEFAULT_SCENES = Path(__file__).with_name('scenes.yaml')
DEFAULT_REFERENCES: tuple[Path, ...] = DATA_FILES

# 자료의 줄의 id 를 만드는 이름 공간. key 에서 만든다(uuid5). 같은 자료면 늘 같은 id 다
REFERENCE_NAMESPACE = uuid.UUID('8a2f6c1e-4b7d-4e9a-a3c5-2d1e0f9b7c64')


class SceneKind(enum.StrEnum):
    """장면의 종류. 결과를 종류별로 나눠 본다."""

    # 그것을 한국어로 부른다(횃불, 고블린)
    NAMED = 'named'
    # 이름 없이 생김새나 쓰임으로만(숨 쉬는 보물 상자)
    MEANING = 'meaning'
    # SRD 에 맞는 것이 없다. 정답이 비어 있다
    NONE = 'none'


class SceneShape(enum.StrEnum):
    """장면의 모양. 서버마다 찾는 글이 다르다."""

    # 게임 서버의 라운드(scene, moves). 장면과 선언들로 찾는다
    ROUND = 'round'
    # 대화 서버의 말들(messages). 마지막 두 말로 찾는다
    TALK = 'talk'


class DatasetError(ValueError):
    """데이터가 틀렸다. 틀린 곳을 모두 담는다."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__('\n'.join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class Scene:
    """
    장면 하나. expected 는 맞다고 보는 줄의 key 들이다. 그중 하나라도 고르면 맞힌 것이다.
    query 는 서버가 찾는 글이다. request 는 라운드의 서술 요청이다(대화의 장면은 None).
    """

    name: str
    set: str
    kind: SceneKind
    shape: SceneShape
    query: str
    request: NarrationRequest | None
    expected: frozenset[str]


@dataclass(frozen=True)
class Dataset:
    """장면들과 자료의 줄들."""

    story: str
    scenes: tuple[Scene, ...]
    references: tuple[StoredReference, ...]


def to_stored(record: ReferenceRecord, source: str) -> StoredReference:
    """자료의 줄을 서버가 고를 때의 모양으로(DB 에서 읽은 줄과 같은 칸). id 는 key 에서 만든다."""
    return StoredReference(
        id=uuid.uuid5(REFERENCE_NAMESPACE, record.key),
        key=record.key,
        name=record.name,
        aliases=list(record.aliases),
        content=record.content,
        kind=record.kind,
        data=dict(record.data),
        name_ko=record.name_ko,
        content_ko=record.content_ko,
        source=source,
        look_ko=record.look_ko,
    )


def read_references(paths: Sequence[Path]) -> tuple[StoredReference, ...]:
    """데이터 파일들의 줄을 차례대로."""
    documents = [read_document(path) for path in paths]
    return tuple(to_stored(record, document.source) for document in documents for record in document.entries)


def scene_problems(raw: dict[str, Any], keys: set[str], seen: set[str]) -> list[str]:
    """장면 하나의 틀린 곳들. 없으면 빈 목록이다."""
    name = raw.get('name', '(이름 없음)')
    problems = [f'{name}: {field} 이(가) 없다' for field in ('name', 'set', 'kind') if not raw.get(field)]
    problems.extend(shape_problems(raw, name))
    if name in seen:
        problems.append(f'{name}: 이름이 겹친다')
    if raw.get('kind') not in {kind.value for kind in SceneKind}:
        problems.append(f'{name}: kind 가 틀렸다({raw.get("kind")})')
    expected = raw.get('expected') or []
    problems.extend(f'{name}: 자료에 없는 key {key}' for key in expected if key not in keys)
    if (raw.get('kind') == SceneKind.NONE) != (not expected):
        problems.append(f'{name}: none 이면 정답이 비고, 아니면 정답이 있어야 한다')
    return problems


def shape_problems(raw: dict[str, Any], name: str) -> list[str]:
    """모양의 틀린 곳들. 라운드(scene 과 moves)와 대화(messages) 중 하나만 있어야 한다."""
    is_round = bool(raw.get('scene') or raw.get('moves'))
    is_talk = 'messages' in raw
    if is_round and is_talk:
        return [f'{name}: 라운드(scene, moves)와 대화(messages)를 함께 적었다']
    if is_talk:
        messages = raw['messages']
        if not isinstance(messages, list) or not messages or not all(isinstance(m, str) and m for m in messages):
            return [f'{name}: messages 는 비지 않은 글의 목록이다']
        return []
    return [f'{name}: {field} 이(가) 없다' for field in ('scene', 'moves') if not raw.get(field)]


def shape_of(raw: dict[str, Any]) -> SceneShape:
    """검사한 장면의 모양."""
    return SceneShape.TALK if 'messages' in raw else SceneShape.ROUND


def round_request(raw: dict[str, Any], story: StoryContext) -> NarrationRequest:
    """라운드 장면의 서술 요청."""
    moves = [Move(character, content) for character, content in raw['moves']]
    return NarrationRequest(round_number=1, scene=raw['scene'], moves=moves, story=story)


def to_scene(raw: dict[str, Any], story: StoryContext) -> Scene:
    """검사한 장면을 찾는 글과(라운드면) 서술 요청을 품은 모양으로."""
    shape = shape_of(raw)
    request = round_request(raw, story) if shape == SceneShape.ROUND else None
    query = round_query(request) if request is not None else talk_query(raw['messages'])
    return Scene(
        name=raw['name'],
        set=raw['set'],
        kind=SceneKind(raw['kind']),
        shape=shape,
        query=query,
        request=request,
        expected=frozenset(raw.get('expected') or []),
    )


def load_dataset(scenes_path: Path = DEFAULT_SCENES, references_paths: Sequence[Path] = DEFAULT_REFERENCES) -> Dataset:
    """장면 파일과 자료 파일들을 읽는다. 장면이 틀렸으면 DatasetError 에 틀린 곳을 모두 담는다."""
    references = read_references(references_paths)
    keys = {reference.key for reference in references}
    raw = yaml.safe_load(scenes_path.read_text(encoding='utf-8'))
    problems: list[str] = []
    seen: set[str] = set()
    for scene in raw.get('scenes', []):
        problems.extend(scene_problems(scene, keys, seen))
        seen.add(scene.get('name', ''))
    if problems:
        raise DatasetError(problems)
    story = StoryContext(title='참고 자료 평가', rating='all', guide=raw.get('story', ''))
    scenes = tuple(to_scene(scene, story) for scene in raw['scenes'])
    return Dataset(story=raw.get('story', ''), scenes=scenes, references=references)


def chosen_sets(dataset: Dataset, sets: Sequence[str] | None) -> Dataset:
    """고른 묶음(set)의 장면만 남긴다. sets 가 비면 그대로다."""
    if not sets:
        return dataset
    return replace(dataset, scenes=tuple(scene for scene in dataset.scenes if scene.set in sets))
