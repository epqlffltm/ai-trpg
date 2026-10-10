# game-server/evals/lore/runner.py

"""
평가를 돌린다. 임베딩 모델로 항목과 질의를 벡터로 바꾸고, 방식마다 고른 것을 점수로 만든다.

모델을 부르는 일(measure)과 점수를 매기는 일(evaluate)을 나눈다.
한 번 잰 거리로 거리 기준을 여러 개 바꿔 가며 다시 매길 수 있다(sweep). 모델을 다시 부르지 않는다.
"""

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.embedder import Embedder
from app.lore.retrieval import MAX_DISTANCE, NEAREST_LIMIT, query_text
from app.lore.texts import batched, entry_text
from evals.lore.dataset import Dataset, Kind
from evals.lore.metrics import Method, Outcome, Ranked, Score, chosen_by, rank, score, score_by_kind

# 거리 기준을 바꿔 가며 볼 값들
SWEEP = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)


@dataclass(frozen=True)
class Measurement:
    """한 모델로 잰 것. 질의마다 항목들과의 거리(가까운 순), 질의 하나를 벡터로 바꾸는 데 걸린 시간(밀리초)."""

    model: str
    ranked: dict[str, list[Ranked]]
    query_ms: list[float]


@dataclass(frozen=True)
class Evaluation:
    """한 거리 기준으로 매긴 점수. 방식마다 전체 점수와 종류별 점수."""

    max_distance: float
    overall: dict[Method, Score]
    by_kind: dict[Method, dict[Kind, Score]]


async def embed_entries(embedder: Embedder, dataset: Dataset) -> dict[uuid.UUID, list[float]]:
    """항목들을 서버와 같은 글(이름, 키워드, 내용)로 바꿔 묶음마다 벡터로 만든다."""
    vectors: dict[uuid.UUID, list[float]] = {}
    for batch in batched(dataset.entries):
        for entry, vector in zip(batch, await embedder.embed([entry_text(entry) for entry in batch]), strict=True):
            vectors[entry.id] = vector
    return vectors


async def measure(embedder: Embedder, dataset: Dataset) -> Measurement:
    """항목과 질의를 벡터로 바꾸고, 질의마다 항목들을 가까운 순으로 늘어놓는다. 질의는 하나씩 보내 시간을 잰다."""
    vectors = await embed_entries(embedder, dataset)
    ranked: dict[str, list[Ranked]] = {}
    query_ms: list[float] = []
    for query in dataset.queries:
        started = time.perf_counter()
        (vector,) = await embedder.embed([query_text(query.request)])
        query_ms.append((time.perf_counter() - started) * 1000)
        ranked[query.id] = rank(vector, dataset.entries, vectors)
    return Measurement(embedder.model, ranked, query_ms)


def outcomes(
    method: Method, dataset: Dataset, measurement: Measurement, max_distance: float, limit: int = NEAREST_LIMIT
) -> list[Outcome]:
    """이 방식으로 질의마다 고른 것."""
    return [
        Outcome(query, chosen_by(method, dataset.entries, query, measurement.ranked[query.id], max_distance, limit))
        for query in dataset.queries
    ]


def evaluate(dataset: Dataset, measurement: Measurement, max_distance: float = MAX_DISTANCE) -> Evaluation:
    """한 거리 기준으로 방식마다 점수를 매긴다."""
    overall = {}
    by_kind = {}
    for method in Method:
        results = outcomes(method, dataset, measurement, max_distance)
        overall[method] = score(results)
        by_kind[method] = score_by_kind(results)
    return Evaluation(max_distance, overall, by_kind)


def sweep(dataset: Dataset, measurement: Measurement, thresholds: Sequence[float] = SWEEP) -> list[Evaluation]:
    """거리 기준을 바꿔 가며 점수를 매긴다. 모델을 다시 부르지 않는다."""
    return [evaluate(dataset, measurement, threshold) for threshold in thresholds]
