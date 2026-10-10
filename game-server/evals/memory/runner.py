# game-server/evals/memory/runner.py

"""
지난 일 검색의 평가를 돌린다. 임베딩 모델로 기억과 질의를 벡터로 바꾸고, 서버의 규칙으로 고른 것을 점수로 만든다.

모델을 부르는 일(measure)과 점수를 매기는 일(evaluate)을 나눈다. 한 번 잰 거리로 거리 기준을 바꿔 가며
다시 매길 수 있다(sweep). 고르는 규칙은 서버의 함수 그대로다(app/memory/retrieval.choose_memories).
"""

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.embedder import Embedder
from app.lore.retrieval import query_text
from app.lore.texts import batched
from app.memory.retrieval import MemoryThresholds, choose_memories, eligible, people_in
from app.memory.texts import memory_text
from evals.lore.dataset import Kind, Query
from evals.lore.metrics import Outcome, Score, cosine_distance, f1, score, score_by_kind
from evals.memory.dataset import MemoryDataset

# 바꿔 가며 볼 거리 기준. 뜻으로 고를 때의 것
DISTANCE_SWEEP = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)
# 인물로 걸린 기억의 상한. inf 는 상한 없음이다
GATE_SWEEP = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, math.inf)


@dataclass(frozen=True)
class Measurement:
    """한 모델로 잰 것. distances 는 질의마다 기억(라운드 번호)과의 거리다."""

    model: str
    distances: dict[str, dict[int, float]]


@dataclass(frozen=True)
class Evaluation:
    """한 규칙으로 매긴 점수. 전체, 종류별, 질의마다 고른 것."""

    thresholds: MemoryThresholds
    overall: Score
    by_kind: dict[Kind, Score]
    outcomes: list[Outcome]

    @property
    def f1(self) -> float:
        return f1(self.overall)


async def measure(embedder: Embedder, dataset: MemoryDataset) -> Measurement:
    """기억들을 서버와 같은 글로 바꿔 묶음마다 벡터로 만들고, 질의를 하나씩 벡터로 바꿔 거리를 잰다."""
    vectors: dict[int, list[float]] = {}
    for batch in batched(dataset.memories):
        for memory, vector in zip(batch, await embedder.embed([memory_text(item) for item in batch]), strict=True):
            vectors[memory.number] = vector
    distances = {}
    for query in dataset.queries:
        (vector,) = await embedder.embed([query_text(query.request)])
        distances[query.id] = {number: cosine_distance(vector, other) for number, other in vectors.items()}
    return Measurement(embedder.model, distances)


def chosen_for(
    dataset: MemoryDataset, query: Query, distances: dict[int, float], thresholds: MemoryThresholds
) -> list[str]:
    """질의 하나에서 서버의 규칙으로 고른 기억들의 번호(글자). 고른 차례대로다."""
    text = query_text(query.request)
    candidates = eligible(dataset.memories, query.request.round_number)
    picked = choose_memories(candidates, people_in(dataset.people, text), distances, thresholds)
    return [str(memory.number) for memory in picked]


def evaluate(dataset: MemoryDataset, measurement: Measurement, thresholds: MemoryThresholds) -> Evaluation:
    """한 규칙으로 모든 질의를 매긴다. 모델을 부르지 않는다."""
    outcomes = [
        Outcome(query, chosen_for(dataset, query, measurement.distances[query.id], thresholds))
        for query in dataset.queries
    ]
    return Evaluation(thresholds, score(outcomes), score_by_kind(outcomes), outcomes)


def sweep(
    dataset: MemoryDataset,
    measurement: Measurement,
    distances: Sequence[float] = DISTANCE_SWEEP,
    gates: Sequence[float] = GATE_SWEEP,
) -> list[Evaluation]:
    """거리 기준과 인물의 상한을 바꿔 가며 매긴다. 같은 잰 것을 다시 쓴다."""
    return [
        evaluate(dataset, measurement, MemoryThresholds(max_distance=distance, keyword_max_distance=gate))
        for distance, gate in itertools.product(distances, gates)
    ]


def best(evaluations: Sequence[Evaluation]) -> Evaluation:
    """
    F1 이 가장 높은 것. 같으면 재현율이 높은 것, 그래도 같으면 거리 기준이 좁은(작은) 것.

    좁은 기준을 고르는 것은 점수가 같다면 관련 없는 지난 일을 덜 넣는 쪽이 낫기 때문이다(토큰과 서술의 엉뚱함).
    """
    return max(
        evaluations,
        key=lambda item: (
            item.f1,
            item.overall.recall or 0.0,
            -item.thresholds.max_distance,
            -item.thresholds.keyword_max_distance,
        ),
    )


def split_distances(dataset: MemoryDataset, measurement: Measurement) -> tuple[list[float], list[float]]:
    """고를 수 있는 기억과 질의의 거리를 둘로 나눈다. 정답인 것, 아닌 것. 둘이 갈리는 곳에 거리 기준을 둔다."""
    right: list[float] = []
    other: list[float] = []
    for query in dataset.queries:
        for memory in eligible(dataset.memories, query.request.round_number):
            distance = measurement.distances[query.id][memory.number]
            (right if str(memory.number) in query.expected else other).append(distance)
    return right, other
