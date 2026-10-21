# trpg-server/evals/references/dataset.py

"""
참고 자료 평가의 데이터(YAML)를 읽고 검사한다.

장면은 사람이 손으로 늘린다. 실수(자료에 없는 key, 칸을 빠뜨림, none 인데 정답이 있음)를 읽을 때 모두 모아 알린다.
장면은 서술 요청(NarrationRequest)으로 바꾼다. 서버의 고르는 함수(app/references/retrieval.py)를 그대로 쓰려는 것이다.
자료의 줄은 데이터 파일(data/references/srd51.json)을 읽은 것이다. DB 에 넣은 것과 같다.
"""

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.references.records import ReferenceRecord, StoredReference, read_document
from app.rounds.narrator import Move, NarrationRequest, StoryContext

# 기본 장면 파일과 자료 파일
DEFAULT_SCENES = Path(__file__).with_name('scenes.yaml')
DEFAULT_REFERENCES = Path(__file__).resolve().parents[2] / 'data' / 'references' / 'srd51.json'

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


class DatasetError(ValueError):
    """데이터가 틀렸다. 틀린 곳을 모두 담는다."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__('\n'.join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class Scene:
    """장면 하나. expected 는 맞다고 보는 줄의 key 들이다. 그중 하나라도 고르면 맞힌 것이다."""

    name: str
    set: str
    kind: SceneKind
    request: NarrationRequest
    expected: frozenset[str]


@dataclass(frozen=True)
class Dataset:
    """장면들과 자료의 줄들."""

    story: str
    scenes: tuple[Scene, ...]
    references: tuple[StoredReference, ...]


def to_stored(record: ReferenceRecord) -> StoredReference:
    """자료의 줄을 서버가 고를 때의 모양으로. id 는 key 에서 만든다."""
    return StoredReference(
        id=uuid.uuid5(REFERENCE_NAMESPACE, record.key),
        key=record.key,
        name=record.name,
        aliases=list(record.aliases),
        content=record.content,
        kind=record.kind,
        data=dict(record.data),
    )


def scene_problems(raw: dict[str, Any], keys: set[str], seen: set[str]) -> list[str]:
    """장면 하나의 틀린 곳들. 없으면 빈 목록이다."""
    name = raw.get('name', '(이름 없음)')
    problems = [
        f'{name}: {field} 이(가) 없다' for field in ('name', 'set', 'kind', 'scene', 'moves') if not raw.get(field)
    ]
    if name in seen:
        problems.append(f'{name}: 이름이 겹친다')
    if raw.get('kind') not in {kind.value for kind in SceneKind}:
        problems.append(f'{name}: kind 가 틀렸다({raw.get("kind")})')
    expected = raw.get('expected') or []
    problems.extend(f'{name}: 자료에 없는 key {key}' for key in expected if key not in keys)
    if (raw.get('kind') == SceneKind.NONE) != (not expected):
        problems.append(f'{name}: none 이면 정답이 비고, 아니면 정답이 있어야 한다')
    return problems


def to_scene(raw: dict[str, Any], story: StoryContext) -> Scene:
    """검사한 장면을 서술 요청을 품은 모양으로."""
    moves = [Move(character, content) for character, content in raw['moves']]
    request = NarrationRequest(round_number=1, scene=raw['scene'], moves=moves, story=story)
    return Scene(
        name=raw['name'],
        set=raw['set'],
        kind=SceneKind(raw['kind']),
        request=request,
        expected=frozenset(raw.get('expected') or []),
    )


def load_dataset(scenes_path: Path = DEFAULT_SCENES, references_path: Path = DEFAULT_REFERENCES) -> Dataset:
    """장면 파일과 자료 파일을 읽는다. 장면이 틀렸으면 DatasetError 에 틀린 곳을 모두 담는다."""
    references = tuple(to_stored(record) for record in read_document(references_path).entries)
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
    scenes = tuple(scene for scene in dataset.scenes if scene.set in sets)
    return Dataset(story=dataset.story, scenes=scenes, references=dataset.references)
