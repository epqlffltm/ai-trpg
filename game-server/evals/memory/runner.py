# game-server/evals/memory/runner.py

"""
지난 일 검색의 평가를 돌린다. 임베딩 모델로 기억과 질의를 벡터로 바꾸고, 서버의 규칙으로 고른 것을 점수로 만든다.

모델을 부르는 일(measure)과 점수를 매기는 일(evaluate)을 나눈다. 한 번 잰 거리로 거리 기준을 바꿔 가며
다시 매길 수 있다(sweep). 고르는 규칙은 서버의 함수 그대로다(app/memory/retrieval.choose_memories).

인물의 이력은 모델을 부르지 않는다. 서버의 함수(app/memory/history.py)로 모은 문장이 정답을 얼마나 담았는지 센다.
"""

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.embedder import Embedder
from app.lore.retrieval import mentions, query_text
from app.lore.texts import batched
from app.memory.history import history_of, scene_lines
from app.memory.retrieval import MemoryThresholds, choose_memories, eligible, people_in
from app.memory.texts import memory_text
from app.rounds.narrator import HistoryLine
from evals.lore.dataset import Kind, Query
from evals.lore.metrics import Outcome, Score, cosine_distance, f1, score, score_by_kind
from evals.memory.dataset import HistoryQuery, MemoryDataset

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


@dataclass(frozen=True)
class HistoryOutcome:
    """
    이력의 질의 하나의 결과. 서버의 함수로 모은 문장들과, 정답 중 찾은 것과 놓친 것.

    놓친 것은 둘로 나눈다. unnamed 는 그 문장에 인물의 이름도 키워드도 없어서 놓친 것(문장 골라내기의 한계),
    cut 은 이름이 있지만 문장 수나 글자 수의 상한에 밀려 놓친 것이다.
    """

    query: HistoryQuery
    chosen: list[HistoryLine]
    found: list[str]
    unnamed: list[str]
    cut: list[str]


def sentence_with(lines: Sequence[HistoryLine], text: str) -> HistoryLine:
    """text 가 든 문장. 데이터를 읽을 때 있는 것을 확인했다."""
    return next(line for line in lines if text in line.text)


def history_outcome(dataset: MemoryDataset, query: HistoryQuery) -> HistoryOutcome:
    """이력의 질의 하나를 서버의 함수로 매긴다. 모델을 부르지 않는다."""
    lines = scene_lines(dataset.rounds, query.round_number)
    chosen = history_of(query.person, lines)
    found = [text for text in query.expected if any(text in line.text for line in chosen)]
    missed = [text for text in query.expected if text not in found]
    unnamed = [text for text in missed if not mentions(query.person, sentence_with(lines, text).text)]
    cut = [text for text in missed if text not in unnamed]
    return HistoryOutcome(query, chosen, found, unnamed, cut)


def history_outcomes(dataset: MemoryDataset) -> list[HistoryOutcome]:
    """이력의 질의 모두."""
    return [history_outcome(dataset, query) for query in dataset.histories]


def history_recall(outcomes: Sequence[HistoryOutcome]) -> float | None:
    """정답인 문장 중 이력에 든 것의 비율. 모든 질의를 합쳐 센다. 질의가 없으면 None."""
    expected = sum(len(outcome.query.expected) for outcome in outcomes)
    if expected == 0:
        return None
    return sum(len(outcome.found) for outcome in outcomes) / expected
