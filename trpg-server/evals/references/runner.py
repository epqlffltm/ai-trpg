# trpg-server/evals/references/runner.py

"""
참고 자료의 검색을 잰다. 임베딩 모델로 자료의 줄과 장면을 벡터로 바꾸고, 서버의 규칙으로 고른 것에 점수를 매긴다.

모델을 부르는 일(measure)과 점수를 매기는 일(evaluate, sweep)을 나눈다.
한 번 잰 거리로 거리 기준을 여러 개 바꿔 가며 다시 매긴다. 모델을 다시 부르지 않는다.

고르는 규칙은 서버의 함수(reference_core/selection.py 의 alias_hits, near_enough, pick)로 짠다.
기본 차례(ALIAS_CAP)는 서버의 choose 와 같다(테스트가 견준다). 평가한 규칙과 도는 규칙이 같다.
DB 의 가까운 순(repository.nearest)만 여기서 같은 셈으로 한다(거리 기준 이하, 가까운 순, limit 개).
로어북은 없다고 본다. 남은 자리는 REFERENCE_MAX_CHARS 다.

지표(로어북 평가와 같은 뜻이다, evals/lore/metrics.py).
  - hit(맞힘): 정답이 있는 장면에서 정답 중 하나라도 고른 비율. 장면마다 정답은 "이 중 하나"다.
  - precision(정밀도): 고른 줄 중 정답인 것의 비율. 정답이 없는 장면에서 고른 것은 모두 틀린 것이다.
  - empty(비우기): 정답이 없는 장면에서 아무것도 고르지 않은 비율.
  - hit@k: 거리 기준 없이 가까운 k 개 안에 정답이 드는 비율. 기준을 고르기 전의 모델의 실력이다.
다른 이름으로 걸린 줄의 거리도 따로 보인다. 다른 이름의 상한(keyword_max_distance)에 잘린 이름을 찾는다.

벡터로 바꿀 자료의 글(EmbeddingText)도 바꿔 가며 잴 수 있다. 서버는 이름과 생김새 글로 만든다(reference_core/texts.py).
전의 글(이름, 다른 이름, 생김새 글 + 규칙 요약)과 견준다. 서술자에게 가는 글은 그대로다(고르기만 잰다).

넣는 차례(Order)도 바꿔 가며 매긴다. 서버는 다른 이름으로 걸린 줄을 limit - 1 줄까지 먼저 넣는다(ALIAS_CAP, 2026-11-26).
전에는 다른 이름을 모두 먼저 넣었다(ALIAS_FIRST). 그 줄들이 자리를 다 채워 뜻으로 더 가까운 정답이 들어가지 못했다.
"""

import enum
import math
import statistics
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from ai_core.embedder import Embedder
from reference_core.records import StoredReference
from reference_core.selection import (
    REFERENCE_MAX_CHARS,
    ReferenceThresholds,
    alias_hits,
    in_order,
    near_enough,
    pick,
)
from reference_core.texts import reference_text

from app.lore.texts import batched
from evals.lore.metrics import cosine_distance
from evals.references.dataset import Dataset, Scene, SceneKind, SceneShape

# 거리 기준을 바꿔 가며 볼 값들
SWEEP_DISTANCES = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80)
# 다른 이름의 상한을 바꿔 가며 볼 값들. 거리 기준은 지금 값 그대로다. inf 는 상한이 없는 것이다
KEYWORD_SWEEP_DISTANCES = (0.50, 0.55, 0.60, 0.65, 0.70, math.inf)
# hit@k 의 k
TOP_KS = (1, 3, 5)
# 넣는 차례를 견줄 때 함께 바꿔 보는 거리 기준
ORDER_DISTANCES = (0.40, 0.45, 0.50)


class EmbeddingText(enum.StrEnum):
    """
    자료의 줄을 벡터로 바꿀 글.
      - CURRENT: 서버와 같다(reference_core/texts.reference_text). 이름과 생김새 글(2026-11-27 부터)
      - WITH_RULES: 이름, 다른 이름, 글(생김새 글 + 규칙 요약). 2026-11-27 전의 서버다
      - WITHOUT_RULES: 이름, 다른 이름, 생김새 글
      - WITHOUT_WIKI_LOOKS: 위키백과의 줄만 생김새 글 전의 글(이름, 다른 이름, 글)이다. 다른 줄은 서버와 같다.
        위키백과의 생김새 글(2026-11-28)이 무엇을 바꿨는지 같은 실행에서 견준다
    생김새 글이 없는 줄은 모두 서버와 같은 글이다.
    """

    CURRENT = 'current'
    WITH_RULES = 'with_rules'
    WITHOUT_RULES = 'without_rules'
    WITHOUT_WIKI_LOOKS = 'without_wiki_looks'


# 보고서의 머리에 적는 글의 이름
EMBEDDING_TEXT_NAMES = {
    EmbeddingText.CURRENT: '지금의 글',
    EmbeddingText.WITH_RULES: '규칙 요약 넣기(전의 글)',
    EmbeddingText.WITHOUT_RULES: '다른 이름 넣기',
    EmbeddingText.WITHOUT_WIKI_LOOKS: '위키백과 생김새 글 빼기(전의 글)',
}


class Order(enum.StrEnum):
    """
    고른 줄을 넣는 차례.
      - ALIAS_FIRST: 다른 이름으로 걸린 줄을 모두 먼저, 그다음 뜻이 가까운 줄(2026-11-26 전의 서버)
      - BY_DISTANCE: 둘을 섞어 거리가 가까운 순. 거리를 모르는 다른 이름의 줄(벡터 없음)이 맨 앞이다
      - ALIAS_CAP: 다른 이름으로 걸린 줄은 limit - 1 줄까지 먼저, 그다음 뜻이 가까운 줄, 남은 다른 이름의 줄은 맨 뒤
        (지금 서버의 규칙, reference_core/selection.in_order)
    """

    ALIAS_FIRST = 'alias_first'
    BY_DISTANCE = 'by_distance'
    ALIAS_CAP = 'alias_cap'


@dataclass(frozen=True)
class Measurement:
    """
    모델 하나로 잰 거리. distances 는 장면의 이름에서, 줄의 id 에서 거리로다.

    seconds 는 모델을 부르는 데 걸린 시간이다(자료와 장면을 벡터로 바꾸기). text 는 자료를 벡터로 바꾼 글이다.
    """

    model: str
    distances: dict[str, dict[uuid.UUID, float]]
    seconds: float
    text: EmbeddingText = EmbeddingText.CURRENT

    @property
    def label(self) -> str:
        """보고서의 머리. 서버와 같은 글이면 모델의 이름만이다."""
        if self.text == EmbeddingText.CURRENT:
            return self.model
        return f'{self.model} · {EMBEDDING_TEXT_NAMES[self.text]}'


@dataclass(frozen=True)
class Outcome:
    """장면 하나에서 고른 것. chosen 은 고른 차례대로의 key 다."""

    scene: Scene
    chosen: list[str]

    @property
    def hit(self) -> bool:
        """정답 중 하나라도 골랐는가."""
        return bool(self.scene.expected & set(self.chosen))


@dataclass(frozen=True)
class Score:
    """규칙 하나의 점수. 장면이 없는 몫은 None 이다."""

    hit: float | None
    precision: float | None
    empty: float | None
    chosen_per_scene: float


@dataclass(frozen=True)
class Closest:
    """장면에서 가장 가까운 정답. rank 는 모든 줄을 가까운 순으로 늘어놓았을 때의 차례다(1 이 가장 가깝다)."""

    key: str
    distance: float
    rank: int


@dataclass(frozen=True)
class Spread:
    """정답과의 거리(장면마다 가장 가까운 정답)와, 정답이 아닌 가장 가까운 줄과의 거리."""

    expected: list[float]
    others: list[float]


async def embed_all(embedder: Embedder, texts: Sequence[str]) -> list[list[float]]:
    """글들을 묶음(32개)마다 벡터로 바꾼다. 실패하면 ProviderError 가 그대로 올라간다."""
    vectors: list[list[float]] = []
    for batch in batched(list(texts)):
        vectors.extend(await embedder.embed(batch))
    return vectors


def embedding_text(reference: StoredReference, text: EmbeddingText) -> str:
    """자료의 줄을 벡터로 바꿀 글. 생김새 글이 없으면 서버와 같은 글이다."""
    if text == EmbeddingText.CURRENT or not reference.look_ko:
        return reference_text(reference)
    if text == EmbeddingText.WITHOUT_WIKI_LOOKS:
        plain = replace(reference, look_ko='') if reference.source == 'wikipedia' else reference
        return reference_text(plain)
    lines = [reference.name]
    if reference.aliases:
        lines.append(f'다른 이름: {", ".join(reference.aliases)}')
    lines.append(reference.shown_content if text == EmbeddingText.WITH_RULES else reference.look_ko)
    return '\n'.join(lines)


async def measure(
    embedder: Embedder,
    dataset: Dataset,
    clock: Callable[[], float] = time.perf_counter,
    text: EmbeddingText = EmbeddingText.CURRENT,
) -> Measurement:
    """
    자료의 줄과 장면을 벡터로 바꿔 장면마다 모든 줄과의 거리를 잰다. text 는 자료를 벡터로 바꿀 글이다.
    clock 은 시간을 재는 함수다(테스트가 바꾼다).
    """
    tick = clock
    started = tick()
    texts = [embedding_text(reference, text) for reference in dataset.references]
    reference_vectors = await embed_all(embedder, texts)
    scene_vectors = await embed_all(embedder, [scene.query for scene in dataset.scenes])
    distances = {
        scene.name: {
            reference.id: cosine_distance(vector, reference_vector)
            for reference, reference_vector in zip(dataset.references, reference_vectors, strict=True)
        }
        for scene, vector in zip(dataset.scenes, scene_vectors, strict=True)
    }
    return Measurement(model=embedder.model, distances=distances, seconds=tick() - started, text=text)


def nearest(
    references: Sequence[StoredReference], distances: dict[uuid.UUID, float], max_distance: float, limit: int
) -> list[StoredReference]:
    """거리가 max_distance 이하인 줄들, 가까운 순으로 limit 개까지. 서버의 repository.nearest 와 같은 셈이다."""
    near = [reference for reference in references if distances.get(reference.id, math.inf) <= max_distance]
    return sorted(near, key=lambda reference: distances[reference.id])[:limit]


def ordered(
    order: Order,
    hits: Sequence[StoredReference],
    near: Sequence[StoredReference],
    distances: dict[uuid.UUID, float],
    limit: int,
) -> list[StoredReference]:
    """
    넣을 차례로 늘어놓은 줄들. hits 는 상한 안의 다른 이름의 줄, near 는 뜻이 가까운 줄이다.
    같은 줄은 pick 이 한 번만 넣는다.
    """
    if order == Order.BY_DISTANCE:
        return sorted([*hits, *near], key=lambda reference: distances.get(reference.id, -math.inf))
    if order == Order.ALIAS_FIRST:
        return [*hits, *near]
    return in_order(hits, near, limit)


def pick_for(
    scene: Scene,
    references: Sequence[StoredReference],
    distances: dict[uuid.UUID, float],
    thresholds: ReferenceThresholds,
    order: Order = Order.ALIAS_CAP,
) -> list[StoredReference]:
    """
    장면 하나에서 고른 줄들. 기본(ALIAS_CAP)은 서버의 규칙(reference_core/selection.choose)과 같다.
    로어북이 없다고 보고 남은 자리는 REFERENCE_MAX_CHARS 다.
    """
    text = scene.query
    hits = [hit for hit in alias_hits(references, text) if near_enough(hit, distances, thresholds.keyword_max_distance)]
    near = nearest(references, distances, thresholds.max_distance, thresholds.limit)
    room = min(REFERENCE_MAX_CHARS, thresholds.max_chars)
    return pick(ordered(order, hits, near, distances, thresholds.limit), room, thresholds.limit)


def evaluate(
    dataset: Dataset, measurement: Measurement, thresholds: ReferenceThresholds, order: Order = Order.ALIAS_CAP
) -> list[Outcome]:
    """장면마다 고른 것."""
    return [
        Outcome(
            scene=scene,
            chosen=[
                ref.key
                for ref in pick_for(scene, dataset.references, measurement.distances[scene.name], thresholds, order)
            ],
        )
        for scene in dataset.scenes
    ]


def ratio(count: int, total: int) -> float | None:
    """비율. 셀 것이 없으면 None 이다."""
    return count / total if total else None


def score(outcomes: Sequence[Outcome]) -> Score:
    """고른 것들의 점수."""
    answered = [outcome for outcome in outcomes if outcome.scene.expected]
    blank = [outcome for outcome in outcomes if not outcome.scene.expected]
    chosen = [key for outcome in outcomes for key in outcome.chosen]
    right = sum(1 for outcome in outcomes for key in outcome.chosen if key in outcome.scene.expected)
    return Score(
        hit=ratio(sum(1 for outcome in answered if outcome.hit), len(answered)),
        precision=ratio(right, len(chosen)),
        empty=ratio(sum(1 for outcome in blank if not outcome.chosen), len(blank)),
        chosen_per_scene=len(chosen) / len(outcomes) if outcomes else 0.0,
    )


def score_by_kind(outcomes: Sequence[Outcome]) -> dict[SceneKind, Score]:
    """장면의 종류마다의 점수. 장면이 없는 종류는 빠진다."""
    kinds = {outcome.scene.kind for outcome in outcomes}
    return {
        kind: score([outcome for outcome in outcomes if outcome.scene.kind == kind])
        for kind in SceneKind
        if kind in kinds
    }


def score_by_shape(outcomes: Sequence[Outcome]) -> dict[SceneShape, Score]:
    """장면의 모양(라운드, 대화)마다의 점수. 장면이 없는 모양은 빠진다."""
    shapes = {outcome.scene.shape for outcome in outcomes}
    return {
        shape: score([outcome for outcome in outcomes if outcome.scene.shape == shape])
        for shape in SceneShape
        if shape in shapes
    }


def sweep(dataset: Dataset, measurement: Measurement, base: ReferenceThresholds) -> list[tuple[float, Score]]:
    """
    거리 기준을 바꿔 가며 매긴 점수.

    다른 이름의 상한은 거리 기준과 지금의 상한 중 큰 것이다. 다른 이름이 비어 있는 동안은 뜻이 없다.
    """
    results = []
    for distance in SWEEP_DISTANCES:
        thresholds = ReferenceThresholds(distance, max(distance, base.keyword_max_distance), base.limit, base.max_chars)
        results.append((distance, score(evaluate(dataset, measurement, thresholds))))
    return results


def sweep_keyword(dataset: Dataset, measurement: Measurement, base: ReferenceThresholds) -> list[tuple[float, Score]]:
    """다른 이름의 상한을 바꿔 가며 매긴 점수. 거리 기준, 줄의 수, 글자 수는 base 그대로다."""
    results = []
    for distance in KEYWORD_SWEEP_DISTANCES:
        thresholds = ReferenceThresholds(base.max_distance, distance, base.limit, base.max_chars)
        results.append((distance, score(evaluate(dataset, measurement, thresholds))))
    return results


def sweep_orders(
    dataset: Dataset, measurement: Measurement, base: ReferenceThresholds
) -> list[tuple[Order, float, Score]]:
    """넣는 차례와 거리 기준(ORDER_DISTANCES)을 함께 바꿔 가며 매긴 점수. 다른 이름의 상한, 줄 수, 글자 수는 base 다."""
    results = []
    for order in Order:
        for distance in ORDER_DISTANCES:
            thresholds = ReferenceThresholds(distance, base.keyword_max_distance, base.limit, base.max_chars)
            results.append((order, distance, score(evaluate(dataset, measurement, thresholds, order))))
    return results


def closest_answer(scene: Scene, dataset: Dataset, measurement: Measurement) -> Closest | None:
    """장면에서 가장 가까운 정답과 그 거리, 모든 줄 가운데의 차례. 정답이 없는 장면은 None 이다."""
    distances = measurement.distances[scene.name]
    ranked = sorted(dataset.references, key=lambda reference: distances[reference.id])
    for rank, reference in enumerate(ranked, start=1):
        if reference.key in scene.expected:
            return Closest(key=reference.key, distance=distances[reference.id], rank=rank)
    return None


def alias_distances(scene: Scene, dataset: Dataset, measurement: Measurement) -> list[tuple[str, float | None]]:
    """장면에서 다른 이름으로 걸린 줄의 key 와 거리. 받은 차례대로다. 거리를 모르면 None 이다."""
    distances = measurement.distances[scene.name]
    hits = alias_hits(dataset.references, scene.query)
    return [(reference.key, distances.get(reference.id)) for reference in hits]


def hit_at(dataset: Dataset, measurement: Measurement, k: int) -> float | None:
    """거리 기준 없이 가까운 k 개 안에 정답이 드는 장면의 비율. 정답이 있는 장면만 센다."""
    answered = [scene for scene in dataset.scenes if scene.expected]
    found = 0
    for scene in answered:
        distances = measurement.distances[scene.name]
        top = sorted(dataset.references, key=lambda reference: distances[reference.id])[:k]
        found += any(reference.key in scene.expected for reference in top)
    return ratio(found, len(answered))


def spread(dataset: Dataset, measurement: Measurement) -> Spread:
    """정답이 있는 장면마다 가장 가까운 정답의 거리와, 모든 장면에서 정답이 아닌 가장 가까운 줄의 거리."""
    expected: list[float] = []
    others: list[float] = []
    for scene in dataset.scenes:
        distances = measurement.distances[scene.name]
        right = [distances[ref.id] for ref in dataset.references if ref.key in scene.expected]
        wrong = [distances[ref.id] for ref in dataset.references if ref.key not in scene.expected]
        if right:
            expected.append(min(right))
        if wrong:
            others.append(min(wrong))
    return Spread(expected=expected, others=others)


def summary(values: Sequence[float]) -> str:
    """거리들의 요약(최소, 중앙, 최대). 없으면 '-' 다."""
    if not values:
        return '-'
    return f'{min(values):.3f} / {statistics.median(values):.3f} / {max(values):.3f}'
