# game-server/evals/lore/narration.py

"""
로어북이 서술에 주는 효과를 보는 도구. scripts/try_narration.py 의 --lore 가 쓴다.

같은 라운드를 셋으로 서술하게 하고 견준다.
  - off:   로어북을 넣지 않는다
  - on:    서버와 같은 규칙(retrieval.choose)과 같은 임베딩 모델로 고른 항목을 넣는다
  - noise: 이 라운드와 상관없는 항목을 넣는다. 모델이 쓸데없는 설정에 끌려가는지 본다

장면이 로어북을 썼는지는 낱말로 어림한다. "로어북에서만 올 수 있는 낱말"(항목의 글에는 있고 로어북을 뺀 프롬프트에는
없는 낱말)이 장면에 나오면 썼다고 본다. 조사를 대충 떼어 내는 어림이라 놓치거나 잘못 잡을 수 있다. 판단은 사람이 한다.

항목은 평가 데이터(evals/lore/chase.yaml)의 것을 쓴다. try_narration 의 예시 라운드와 같은 세계다.
"""

import enum
import math
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.ai.embedder import Embedder
from app.ai.provider import ChatMessage, ProviderError
from app.assets.scenarios.snapshot import EntrySnapshot
from app.lore.retrieval import Thresholds, choose, query_text, scene_labels, to_note
from app.lore.texts import batched, entry_text
from app.rounds.narrator import LoreNote, NarrationRequest
from evals.lore.metrics import cosine_distance

# 예시 라운드(톨게이트, 리무진, 사이렌)와 상관없는 항목들. 키워드도 겹치지 않는다(테스트가 지킨다)
NOISE_NAMES = ('블랙홀 터널', '얼음 결정', '별빛 연료')
# 낱말 끝에서 떼어 낼 조사와 어미. 긴 것부터 본다
ENDINGS = ('에서', '으로', '이다', '에는', '이', '가', '은', '는', '을', '를', '에', '의', '로', '도', '와', '과', '다')
# 서버의 기본 거리 기준(LORE_MAX_DISTANCE, LORE_KEYWORD_MAX_DISTANCE 의 기본값과 같다)
SERVER_THRESHOLDS = Thresholds()
# 한글 낱말
HANGUL_WORD = re.compile(r'[가-힣]+')


class LoreMode(enum.StrEnum):
    """서술에 로어북을 어떻게 넣나."""

    OFF = 'off'
    ON = 'on'
    NOISE = 'noise'


@dataclass(frozen=True)
class LoreSets:
    """
    넣을 항목들. on 은 검색이 고른 것, noise 는 상관없는 것.

    distances 는 항목마다 찾는 글과의 거리다. 임베딩이 실패했으면 비어 있다(on 은 키워드로만 고른 것이 된다).
    labels 는 인물 항목의 이름을 장면의 호칭으로 바꾼 것이다(서버의 LoreRetriever.find 와 같다).
    """

    on: list[EntrySnapshot]
    noise: list[EntrySnapshot]
    distances: dict[uuid.UUID, float]
    labels: dict[str, str] = field(default_factory=dict)


def stem(word: str) -> str:
    """낱말 끝의 조사나 어미 하나를 뗀다. 떼고 나서 두 글자가 안 되면 그대로 둔다."""
    for ending in ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 2:
            return word[: -len(ending)]
    return word


def words_of(text: str) -> set[str]:
    """글의 한글 낱말들(조사를 뗀 것). 한 글자짜리는 뺀다."""
    return {stemmed for word in HANGUL_WORD.findall(text) if len(stemmed := stem(word)) >= 2}


def prompt_text(messages: Iterable[ChatMessage]) -> str:
    """메시지들의 글을 이어 붙인 것."""
    return '\n'.join(message.content for message in messages)


def lore_only_words(entries: Iterable[EntrySnapshot], base: str) -> set[str]:
    """항목들의 이름과 내용에는 있고 base(로어북을 뺀 프롬프트)에는 없는 낱말들. 장면에 나오면 로어북에서 온 것이다."""
    words = {word for entry in entries for word in words_of(f'{entry.name} {entry.content}')}
    return {word for word in words if word not in base}


def used_words(scene: str, words: Iterable[str]) -> list[str]:
    """words 중 장면에 나온 것들. 가나다순."""
    return sorted(word for word in words if word in scene)


async def entry_distances(embedder: Embedder, entries: Sequence[EntrySnapshot], text: str) -> dict[uuid.UUID, float]:
    """
    항목마다 text 와의 코사인 거리. 서버와 같은 글(이름, 키워드, 내용)로 항목을 벡터로 바꾼다.

    임베딩이 실패하면 빈 사전이다. 서버도 그때는 거리를 모른 채 키워드로만 고른다.
    """
    try:
        vectors: dict[uuid.UUID, list[float]] = {}
        for batch in batched(entries):
            for entry, vector in zip(batch, await embedder.embed([entry_text(entry) for entry in batch]), strict=True):
                vectors[entry.id] = vector
        (query,) = await embedder.embed([text])
    except ProviderError:
        return {}
    return {entry_id: cosine_distance(query, vector) for entry_id, vector in vectors.items()}


def select_noise(entries: Sequence[EntrySnapshot], names: Sequence[str] = NOISE_NAMES) -> list[EntrySnapshot]:
    """이름으로 상관없는 항목들을 고른다. 데이터에 없는 이름이 있으면 ValueError(데이터가 바뀌었다)."""
    by_name = {entry.name: entry for entry in entries}
    missing = [name for name in names if name not in by_name]
    if missing:
        raise ValueError(f'평가 데이터에 없는 항목: {", ".join(missing)}')
    return [by_name[name] for name in names]


async def lore_sets(
    embedder: Embedder,
    entries: list[EntrySnapshot],
    request: NarrationRequest,
    thresholds: Thresholds = SERVER_THRESHOLDS,
) -> LoreSets:
    """on 과 noise 의 항목들. on 은 서버와 같은 찾는 글, 같은 규칙으로 고르고 같은 이름표를 쓴다."""
    text = query_text(request)
    distances = await entry_distances(embedder, entries, text)
    labels = scene_labels(entries, text)
    return LoreSets(choose(entries, text, distances, thresholds), select_noise(entries), distances, labels)


def notes_for(mode: LoreMode, sets: LoreSets) -> list[LoreNote]:
    """이 방식으로 서술에 넣을 항목들."""
    if mode == LoreMode.ON:
        return [to_note(entry, sets.labels) for entry in sets.on]
    if mode == LoreMode.NOISE:
        return [to_note(entry, sets.labels) for entry in sets.noise]
    return []


def describe_sets(sets: LoreSets) -> str:
    """고른 항목들을 한 줄씩. 거리를 알면 함께 적는다."""

    def label(entry: EntrySnapshot) -> str:
        distance = sets.distances.get(entry.id, math.nan)
        return entry.name if math.isnan(distance) else f'{entry.name}({distance:.2f})'

    known = '' if sets.distances else ' (임베딩 실패: 서버처럼 키워드로만 골랐다)'
    lines = [
        f'on: {", ".join(map(label, sets.on)) or "없음"}{known}',
        f'noise: {", ".join(map(label, sets.noise))}',
    ]
    if sets.labels:
        lines.append(f'이름표: {", ".join(f"{name} → {shown}" for name, shown in sets.labels.items())}')
    return '\n'.join(lines)
