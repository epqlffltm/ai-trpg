# game-server/evals/lore/metrics.py

"""
검색을 평가하는 순수한 계산. 모델도 DB 도 모른다. 벡터와 정답만 받는다.

거리는 서버와 같은 코사인 거리다(pgvector 의 <=>, app/lore/repository.py). 고르는 규칙도 서버의 함수를 그대로 쓴다.
  - keyword: 이름이나 키워드가 나온 항목만
  - vector:  가까운 순으로 limit 개, 거리 max_distance 이하만
  - hybrid:  키워드를 먼저, 그다음 가까운 순(서버가 실제로 쓰는 것, retrieval.choose)
셋 다 마지막에 글자 수 상한(retrieval.pick)을 지킨다.

지표.
  - recall(재현율): 맞는 항목 중 고른 것의 비율. 정답이 있는 질의만 평균한다. 놓치면 AI 가 설정을 모른다.
  - precision(정밀도): 고른 것 중 맞는 것의 비율. 모든 질의에서 고른 것을 다 모아 센다.
    정답이 없는 질의에서 고른 것은 모두 틀린 것이다. 틀린 것을 넣으면 토큰이 들고 서술이 엉뚱해진다.
  - mrr: 맞는 항목이 처음 나온 자리의 역수의 평균. 1 이면 늘 첫째에 있다.
  - empty: 정답이 없는 질의에서 아무것도 고르지 않은 비율.
"""

import enum
import math
import statistics
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.assets.scenarios.snapshot import EntrySnapshot
from app.lore.retrieval import choose, keyword_hits, pick, query_text
from evals.lore.dataset import Kind, Query


class Method(enum.StrEnum):
    """고르는 방식."""

    KEYWORD = 'keyword'
    VECTOR = 'vector'
    HYBRID = 'hybrid'


@dataclass(frozen=True)
class Ranked:
    """질의와 항목 하나의 거리."""

    entry: EntrySnapshot
    distance: float


@dataclass(frozen=True)
class Outcome:
    """질의 하나에서 고른 것. chosen 은 고른 차례대로의 항목 이름이다."""

    query: Query
    chosen: list[str]


@dataclass(frozen=True)
class Score:
    """질의 묶음 하나의 점수. 셀 질의가 없으면 그 칸은 None 이다."""

    recall: float | None
    precision: float | None
    mrr: float | None
    empty: float | None
    queries: int


def cosine_distance(left: Sequence[float], right: Sequence[float]) -> float:
    """코사인 거리. 0 이면 같은 방향, 1 이면 직각, 2 면 반대다. 길이가 0 인 벡터는 1 로 친다."""
    norms = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    if norms == 0:
        return 1.0
    return 1.0 - sum(a * b for a, b in zip(left, right, strict=True)) / norms


def rank(
    query_vector: Sequence[float], entries: list[EntrySnapshot], vectors: dict[uuid.UUID, list[float]]
) -> list[Ranked]:
    """항목들을 질의와 가까운 순으로. 벡터가 없는 항목은 뺀다."""
    ranked = [
        Ranked(entry, cosine_distance(query_vector, vectors[entry.id])) for entry in entries if entry.id in vectors
    ]
    return sorted(ranked, key=lambda item: item.distance)


def nearest_within(ranked: list[Ranked], max_distance: float, limit: int) -> list[EntrySnapshot]:
    """가까운 순으로 limit 개까지, 거리가 max_distance 이하인 것만. 서버의 nearest_entry_ids 와 같은 규칙이다."""
    return [item.entry for item in ranked if item.distance <= max_distance][:limit]


def chosen_by(
    method: Method, entries: list[EntrySnapshot], query: Query, ranked: list[Ranked], max_distance: float, limit: int
) -> list[str]:
    """이 방식으로 고른 항목의 이름들. 고른 차례대로다."""
    text = query_text(query.request)
    if method == Method.KEYWORD:
        picked = pick(keyword_hits(entries, text))
    elif method == Method.VECTOR:
        picked = pick(nearest_within(ranked, max_distance, limit))
    else:
        picked = choose(entries, text, nearest_within(ranked, max_distance, limit))
    return [entry.name for entry in picked]


def recall(chosen: list[str], expected: frozenset[str]) -> float | None:
    """맞는 항목 중 고른 것의 비율. 정답이 없으면 None."""
    if not expected:
        return None
    return len(expected.intersection(chosen)) / len(expected)


def reciprocal_rank(chosen: list[str], expected: frozenset[str]) -> float | None:
    """맞는 항목이 처음 나온 자리의 역수. 하나도 없으면 0, 정답이 없으면 None."""
    if not expected:
        return None
    for position, name in enumerate(chosen, start=1):
        if name in expected:
            return 1.0 / position
    return 0.0


def mean(values: list[float | None]) -> float | None:
    """None 을 뺀 평균. 남는 것이 없으면 None."""
    present = [value for value in values if value is not None]
    return statistics.fmean(present) if present else None


def micro_precision(outcomes: list[Outcome]) -> float | None:
    """모든 질의에서 고른 것을 모아, 그중 맞는 것의 비율. 아무것도 고르지 않았으면 None."""
    chosen = sum(len(outcome.chosen) for outcome in outcomes)
    if chosen == 0:
        return None
    correct = sum(len(outcome.query.expected.intersection(outcome.chosen)) for outcome in outcomes)
    return correct / chosen


def empty_rate(outcomes: list[Outcome]) -> float | None:
    """정답이 없는 질의 중 아무것도 고르지 않은 비율. 그런 질의가 없으면 None."""
    negatives = [outcome for outcome in outcomes if not outcome.query.expected]
    if not negatives:
        return None
    return sum(1 for outcome in negatives if not outcome.chosen) / len(negatives)


def score(outcomes: list[Outcome]) -> Score:
    """질의 묶음 하나의 점수."""
    return Score(
        recall=mean([recall(outcome.chosen, outcome.query.expected) for outcome in outcomes]),
        precision=micro_precision(outcomes),
        mrr=mean([reciprocal_rank(outcome.chosen, outcome.query.expected) for outcome in outcomes]),
        empty=empty_rate(outcomes),
        queries=len(outcomes),
    )


def score_by_kind(outcomes: list[Outcome]) -> dict[Kind, Score]:
    """질의의 종류마다 점수. 그 종류의 질의가 없으면 빠진다."""
    scores = {}
    for kind in Kind:
        same = [outcome for outcome in outcomes if outcome.query.kind == kind]
        if same:
            scores[kind] = score(same)
    return scores


def f1(score_: Score) -> float:
    """재현율과 정밀도의 조화 평균. 둘 중 하나가 없거나 0 이면 0."""
    if not score_.recall or not score_.precision:
        return 0.0
    return 2 * score_.recall * score_.precision / (score_.recall + score_.precision)


def ranking_recall_at(ranked_by_query: dict[str, list[Ranked]], queries: list[Query], k: int) -> float | None:
    """
    거리 기준 없이 가까운 순 k 개 안에 맞는 항목이 몇이나 드는가(재현율@k). 정답이 있는 질의만 평균한다.

    벡터의 순서 자체가 좋은지 본다. 거리 기준을 고르기 전의, 모델의 실력이다.
    """
    values = []
    for query in queries:
        top = [item.entry.name for item in ranked_by_query[query.id][:k]]
        values.append(recall(top, query.expected))
    return mean(values)


def split_distances(ranked_by_query: dict[str, list[Ranked]], queries: list[Query]) -> tuple[list[float], list[float]]:
    """
    거리를 둘로 나눈다. 맞는 항목과의 거리, 그 밖의 항목과의 거리.

    두 분포가 겹치지 않는 곳에 거리 기준을 두면 맞는 것은 들이고 틀린 것은 막는다.
    """
    relevant: list[float] = []
    other: list[float] = []
    for query in queries:
        for item in ranked_by_query[query.id]:
            (relevant if item.entry.name in query.expected else other).append(item.distance)
    return relevant, other


def five_numbers(values: list[float]) -> tuple[float, float, float, float, float] | None:
    """최솟값, 25%, 중앙값, 75%, 최댓값. 값이 없으면 None. 하나면 다섯 칸이 모두 그 값이다."""
    if not values:
        return None
    if len(values) == 1:
        return (values[0],) * 5
    low, middle, high = statistics.quantiles(values, n=4, method='inclusive')
    return min(values), low, middle, high, max(values)
