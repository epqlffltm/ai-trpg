# trpg-server/evals/references/runner.py

"""
참고 자료의 검색을 잰다. 임베딩 모델로 자료의 줄과 장면을 벡터로 바꾸고, 서버의 규칙으로 고른 것에 점수를 매긴다.

모델을 부르는 일(measure)과 점수를 매기는 일(evaluate, sweep)을 나눈다.
한 번 잰 거리로 거리 기준을 여러 개 바꿔 가며 다시 매긴다. 모델을 다시 부르지 않는다.

고르는 규칙은 서버의 함수(app/references/retrieval.py 의 alias_hits, choose)를 그대로 쓴다.
평가한 규칙과 도는 규칙이 같다.
DB 의 가까운 순(repository.nearest)만 여기서 같은 셈으로 한다(거리 기준 이하, 가까운 순, limit 개).
로어북은 없다고 본다. 남은 자리는 REFERENCE_MAX_CHARS 다.

지표(로어북 평가와 같은 뜻이다, evals/lore/metrics.py).
  - hit(맞힘): 정답이 있는 장면에서 정답 중 하나라도 고른 비율. 장면마다 정답은 "이 중 하나"다.
  - precision(정밀도): 고른 줄 중 정답인 것의 비율. 정답이 없는 장면에서 고른 것은 모두 틀린 것이다.
  - empty(비우기): 정답이 없는 장면에서 아무것도 고르지 않은 비율.
  - hit@k: 거리 기준 없이 가까운 k 개 안에 정답이 드는 비율. 기준을 고르기 전의 모델의 실력이다.
"""

import math
import statistics
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.ai.embedder import Embedder
from app.lore.retrieval import query_text
from app.lore.texts import batched
from app.references.records import StoredReference
from app.references.retrieval import (
    REFERENCE_MAX_CHARS,
    ReferenceThresholds,
    alias_hits,
    choose,
)
from app.references.texts import reference_text
from evals.lore.metrics import cosine_distance
from evals.references.dataset import Dataset, Scene, SceneKind

# 거리 기준을 바꿔 가며 볼 값들
SWEEP_DISTANCES = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80)
# hit@k 의 k
TOP_KS = (1, 3, 5)


@dataclass(frozen=True)
class Measurement:
    """
    모델 하나로 잰 거리. distances 는 장면의 이름에서, 줄의 id 에서 거리로다.

    seconds 는 모델을 부르는 데 걸린 시간이다(자료와 장면을 벡터로 바꾸기).
    """

    model: str
    distances: dict[str, dict[uuid.UUID, float]]
    seconds: float


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


async def measure(embedder: Embedder, dataset: Dataset, clock: Callable[[], float] = time.perf_counter) -> Measurement:
    """자료의 줄과 장면을 벡터로 바꿔 장면마다 모든 줄과의 거리를 잰다. clock 은 시간을 재는 함수다(테스트가 바꾼다)."""
    tick = clock
    started = tick()
    reference_vectors = await embed_all(embedder, [reference_text(reference) for reference in dataset.references])
    scene_vectors = await embed_all(embedder, [query_text(scene.request) for scene in dataset.scenes])
    distances = {
        scene.name: {
            reference.id: cosine_distance(vector, reference_vector)
            for reference, reference_vector in zip(dataset.references, reference_vectors, strict=True)
        }
        for scene, vector in zip(dataset.scenes, scene_vectors, strict=True)
    }
    return Measurement(model=embedder.model, distances=distances, seconds=tick() - started)


def nearest(
    references: Sequence[StoredReference], distances: dict[uuid.UUID, float], max_distance: float, limit: int
) -> list[StoredReference]:
    """거리가 max_distance 이하인 줄들, 가까운 순으로 limit 개까지. 서버의 repository.nearest 와 같은 셈이다."""
    near = [reference for reference in references if distances.get(reference.id, math.inf) <= max_distance]
    return sorted(near, key=lambda reference: distances[reference.id])[:limit]


def pick_for(
    scene: Scene,
    references: Sequence[StoredReference],
    distances: dict[uuid.UUID, float],
    thresholds: ReferenceThresholds,
) -> list[StoredReference]:
    """장면 하나에서 서버의 규칙으로 고른 줄들. 로어북이 없다고 보고 남은 자리는 REFERENCE_MAX_CHARS 다."""
    text = query_text(scene.request)
    hits = alias_hits(references, text)
    near = nearest(references, distances, thresholds.max_distance, thresholds.limit)
    return choose(hits, distances, near, thresholds, min(REFERENCE_MAX_CHARS, thresholds.max_chars))


def evaluate(dataset: Dataset, measurement: Measurement, thresholds: ReferenceThresholds) -> list[Outcome]:
    """장면마다 고른 것."""
    return [
        Outcome(
            scene=scene,
            chosen=[
                ref.key for ref in pick_for(scene, dataset.references, measurement.distances[scene.name], thresholds)
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
