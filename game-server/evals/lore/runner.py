# game-server/evals/lore/runner.py

"""
평가를 돌린다. 임베딩 모델로 항목과 질의를 벡터로 바꾸고, 방식마다 고른 것을 점수로 만든다.

모델을 부르는 일(measure)과 점수를 매기는 일(evaluate)을 나눈다.
한 번 잰 거리로 거리 기준을 여러 개 바꿔 가며 다시 매길 수 있다(sweep, sweep_gates). 모델을 다시 부르지 않는다.

키워드로 걸린 항목은 두 가지 거리를 미리 재 둔다. 질의 전체와의 거리(ranked 에 있다),
키워드가 나온 문장과의 거리(windows). 키워드에 상한을 두는 방식(gated, windowed)이 쓴다.
"""

import math
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.embedder import Embedder
from app.assets.scenarios.snapshot import EntrySnapshot
from app.lore.retrieval import MAX_DISTANCE, keyword_hits, query_text
from app.lore.texts import batched, entry_text
from evals.lore.dataset import Dataset, Kind, Query
from evals.lore.metrics import (
    GATED_METHODS,
    PLAIN_METHODS,
    Method,
    Outcome,
    Ranked,
    Rule,
    Score,
    chosen_by,
    cosine_distance,
    rank,
    score,
    score_by_kind,
)
from evals.lore.windows import windows_for

# 거리 기준을 바꿔 가며 볼 값들
SWEEP = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
# 키워드의 상한을 바꿔 가며 볼 값들. 짧은 문장과 긴 항목의 거리는 질의 전체보다 멀 수 있어 더 넓게 본다
GATE_SWEEP = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


@dataclass(frozen=True)
class Measurement:
    """
    한 모델로 잰 것.

    ranked: 질의마다 항목들과의 거리(가까운 순)
    windows: 질의마다 키워드로 걸린 항목과, 키워드가 나온 문장과의 거리(문장이 여럿이면 가장 가까운 것)
    query_ms: 질의 하나를 벡터로 바꾸는 데 걸린 시간(밀리초)
    window_ms: 질의 하나의 문장들을 벡터로 바꾸는 데 걸린 시간. 걸린 항목이 있는 질의만
    """

    model: str
    ranked: dict[str, list[Ranked]]
    windows: dict[str, dict[uuid.UUID, float]]
    query_ms: list[float]
    window_ms: list[float]


@dataclass(frozen=True)
class Evaluation:
    """한 규칙으로 매긴 점수. 방식마다 전체 점수와 종류별 점수."""

    rule: Rule
    overall: dict[Method, Score]
    by_kind: dict[Method, dict[Kind, Score]]

    @property
    def max_distance(self) -> float:
        """벡터로 고를 때의 거리 기준."""
        return self.rule.max_distance


async def embed_entries(embedder: Embedder, dataset: Dataset) -> dict[uuid.UUID, list[float]]:
    """항목들을 서버와 같은 글(이름, 키워드, 내용)로 바꿔 묶음마다 벡터로 만든다."""
    vectors: dict[uuid.UUID, list[float]] = {}
    for batch in batched(dataset.entries):
        for entry, vector in zip(batch, await embedder.embed([entry_text(entry) for entry in batch]), strict=True):
            vectors[entry.id] = vector
    return vectors


def window_pairs(entries: list[EntrySnapshot], query: Query) -> list[tuple[EntrySnapshot, str]]:
    """키워드로 걸린 항목과 그 키워드가 나온 문장의 짝들."""
    text = query_text(query.request)
    return [(entry, window) for entry in keyword_hits(entries, text) for window in windows_for(entry, text)]


async def window_distances(
    embedder: Embedder, pairs: list[tuple[EntrySnapshot, str]], vectors: dict[uuid.UUID, list[float]]
) -> dict[uuid.UUID, float]:
    """짝들의 문장을 한 번에 벡터로 바꿔 항목과의 거리를 잰다. 같은 문장은 한 번만 보낸다. 항목마다 가장 가까운 것."""
    texts = list(dict.fromkeys(window for _, window in pairs))
    embedded = dict(zip(texts, await embedder.embed(texts), strict=True))
    distances: dict[uuid.UUID, float] = {}
    for entry, window in pairs:
        distance = cosine_distance(embedded[window], vectors[entry.id])
        distances[entry.id] = min(distance, distances.get(entry.id, math.inf))
    return distances


def elapsed_ms(started: float) -> float:
    """started(perf_counter) 부터 지금까지의 밀리초."""
    return (time.perf_counter() - started) * 1000


async def measure(embedder: Embedder, dataset: Dataset) -> Measurement:
    """
    항목과 질의를 벡터로 바꾸고, 질의마다 항목들을 가까운 순으로 늘어놓는다.

    키워드로 걸린 항목이 있으면 그 문장들도 벡터로 바꿔 거리를 잰다. 질의와 문장은 따로 보내 시간을 나눠 잰다.
    """
    vectors = await embed_entries(embedder, dataset)
    ranked: dict[str, list[Ranked]] = {}
    windows: dict[str, dict[uuid.UUID, float]] = {}
    query_ms: list[float] = []
    window_ms: list[float] = []
    for query in dataset.queries:
        started = time.perf_counter()
        (vector,) = await embedder.embed([query_text(query.request)])
        query_ms.append(elapsed_ms(started))
        ranked[query.id] = rank(vector, dataset.entries, vectors)
        pairs = window_pairs(dataset.entries, query)
        windows[query.id] = {}
        if pairs:
            started = time.perf_counter()
            windows[query.id] = await window_distances(embedder, pairs, vectors)
            window_ms.append(elapsed_ms(started))
    return Measurement(embedder.model, ranked, windows, query_ms, window_ms)


def outcomes(method: Method, dataset: Dataset, measurement: Measurement, rule: Rule) -> list[Outcome]:
    """이 방식으로 질의마다 고른 것."""
    return [
        Outcome(
            query,
            chosen_by(
                method, dataset.entries, query, measurement.ranked[query.id], measurement.windows[query.id], rule
            ),
        )
        for query in dataset.queries
    ]


def evaluate_methods(dataset: Dataset, measurement: Measurement, rule: Rule, methods: Sequence[Method]) -> Evaluation:
    """한 규칙으로 이 방식들의 점수를 매긴다."""
    overall = {}
    by_kind = {}
    for method in methods:
        results = outcomes(method, dataset, measurement, rule)
        overall[method] = score(results)
        by_kind[method] = score_by_kind(results)
    return Evaluation(rule, overall, by_kind)


def evaluate(dataset: Dataset, measurement: Measurement, max_distance: float = MAX_DISTANCE) -> Evaluation:
    """한 거리 기준으로 키워드에 상한을 두지 않는 방식들의 점수를 매긴다."""
    return evaluate_methods(dataset, measurement, Rule(max_distance), PLAIN_METHODS)


def sweep(dataset: Dataset, measurement: Measurement, thresholds: Sequence[float] = SWEEP) -> list[Evaluation]:
    """거리 기준을 바꿔 가며 점수를 매긴다. 모델을 다시 부르지 않는다."""
    return [evaluate(dataset, measurement, threshold) for threshold in thresholds]


def sweep_gates(
    dataset: Dataset, measurement: Measurement, max_distance: float, gates: Sequence[float] = GATE_SWEEP
) -> list[Evaluation]:
    """벡터의 거리 기준은 두고, 키워드의 상한을 바꿔 가며 상한을 두는 방식들의 점수를 매긴다."""
    return [evaluate_methods(dataset, measurement, Rule(max_distance, gate), GATED_METHODS) for gate in gates]
