# game-server/evals/lore/report.py

"""
평가 결과를 마크다운 표로 만든다. 순수한 함수다. 표는 콘솔에 찍고, --out 이면 파일로도 남긴다(scripts/eval_lore.py).

모델 하나의 보고서.
  1. 방식마다의 점수(지금 서버의 거리 기준으로)
  2. 서버가 쓰는 방식(hybrid)의 종류별 점수
  3. 벡터의 순서 자체(거리 기준 없이 가까운 k 개)
  4. 맞는 항목과 그 밖의 항목의 거리 분포
  5. 거리 기준을 바꿔 가며 본 hybrid 의 점수와, 가장 나은 기준
  6. 틀린 질의들(무엇을 놓쳤고 무엇을 잘못 넣었나)
  7. 질의 하나를 벡터로 바꾸는 시간
"""

import statistics
from dataclasses import dataclass

from evals.lore.dataset import Dataset
from evals.lore.metrics import Method, f1, five_numbers, ranking_recall_at, split_distances
from evals.lore.runner import Evaluation, Measurement, outcomes

# 벡터의 순서를 볼 k 들
RANK_KS = (1, 3, 5)


@dataclass(frozen=True)
class ModelResult:
    """모델 하나의 결과. 지금의 거리 기준으로 매긴 것, 기준을 바꿔 가며 매긴 것."""

    measurement: Measurement
    current: Evaluation
    swept: list[Evaluation]


def ratio(value: float | None) -> str:
    """0~1 의 값을 소수 둘째 자리로. 없으면 '-'."""
    return '-' if value is None else f'{value:.2f}'


def table(header: list[str], rows: list[list[str]]) -> str:
    """마크다운 표."""
    lines = ['| ' + ' | '.join(header) + ' |', '| ' + ' | '.join('---' for _ in header) + ' |']
    lines.extend('| ' + ' | '.join(row) + ' |' for row in rows)
    return '\n'.join(lines)


def best(swept: list[Evaluation]) -> Evaluation:
    """hybrid 의 F1 이 가장 높은 기준. 같으면 아무것도 넣지 않아야 할 때 더 잘 비우는 것, 그것도 같으면 작은 기준."""
    return max(
        swept,
        key=lambda item: (
            f1(item.overall[Method.HYBRID]),
            item.overall[Method.HYBRID].empty or 0.0,
            -item.max_distance,
        ),
    )


def method_table(evaluation: Evaluation) -> str:
    """방식마다의 점수."""
    rows = []
    for method, score_ in evaluation.overall.items():
        values = [score_.recall, score_.precision, score_.mrr, score_.empty]
        rows.append([method.value, *map(ratio, values), ratio(f1(score_))])
    return table(['방식', '재현율', '정밀도', 'MRR', '비우기', 'F1'], rows)


def kind_table(evaluation: Evaluation, method: Method = Method.HYBRID) -> str:
    """한 방식의 종류별 점수."""
    rows = [
        [kind.value, str(score_.queries), ratio(score_.recall), ratio(score_.precision), ratio(score_.empty)]
        for kind, score_ in evaluation.by_kind[method].items()
    ]
    return table(['종류', '질의', '재현율', '정밀도', '비우기'], rows)


def ranking_table(dataset: Dataset, measurement: Measurement) -> str:
    """거리 기준 없이 가까운 k 개 안에 맞는 항목이 드는 비율."""
    values = [ratio(ranking_recall_at(measurement.ranked, dataset.queries, k)) for k in RANK_KS]
    return table([f'재현율@{k}' for k in RANK_KS], [values])


def distance_table(dataset: Dataset, measurement: Measurement) -> str:
    """맞는 항목과의 거리, 그 밖의 항목과의 거리의 분포."""
    relevant, other = split_distances(measurement.ranked, dataset.queries)
    rows = []
    for label, values in (('맞는 항목', relevant), ('그 밖의 항목', other)):
        numbers = five_numbers(values)
        cells = ['-'] * 5 if numbers is None else [f'{value:.3f}' for value in numbers]
        rows.append([label, str(len(values)), *cells])
    return table(['', '개수', '최소', '25%', '중앙', '75%', '최대'], rows)


def sweep_table(swept: list[Evaluation]) -> str:
    """거리 기준마다 hybrid 의 점수. 가장 나은 기준에 표시를 붙인다."""
    chosen = best(swept)
    rows = []
    for item in swept:
        score_ = item.overall[Method.HYBRID]
        mark = ' ←' if item is chosen else ''
        cells = [ratio(score_.recall), ratio(score_.precision), ratio(score_.empty), ratio(f1(score_))]
        rows.append([f'{item.max_distance:.2f}{mark}', *cells])
    return table(['거리 기준', '재현율', '정밀도', '비우기', 'F1'], rows)


def miss_lines(dataset: Dataset, result: ModelResult) -> list[str]:
    """지금의 기준으로 hybrid 가 틀린 질의들. 놓친 것과 잘못 넣은 것을 적는다."""
    lines = []
    for outcome in outcomes(Method.HYBRID, dataset, result.measurement, result.current.max_distance):
        missed = sorted(outcome.query.expected.difference(outcome.chosen))
        wrong = [name for name in outcome.chosen if name not in outcome.query.expected]
        if missed or wrong:
            detail = f'놓침 {missed}' if missed else ''
            detail += (', ' if missed and wrong else '') + (f'잘못 넣음 {wrong}' if wrong else '')
            lines.append(f'- {outcome.query.id} ({outcome.query.kind.value}): {detail}')
    return lines or ['- 없음']


def latency_line(measurement: Measurement) -> str:
    """질의 하나를 벡터로 바꾸는 시간의 중앙값과 최댓값."""
    if not measurement.query_ms:
        return '질의가 없다'
    return f'중앙 {statistics.median(measurement.query_ms):.0f}ms, 최대 {max(measurement.query_ms):.0f}ms'


def model_report(dataset: Dataset, result: ModelResult) -> str:
    """모델 하나의 보고서."""
    model = result.measurement.model
    current = result.current.max_distance
    parts = [
        f'## {model}',
        f'### 방식마다 (거리 기준 {current:.2f})',
        method_table(result.current),
        '### hybrid 의 종류별',
        kind_table(result.current),
        '### 벡터의 순서 (거리 기준 없이)',
        ranking_table(dataset, result.measurement),
        '### 거리 분포',
        distance_table(dataset, result.measurement),
        '### 거리 기준을 바꿔 가며 (hybrid)',
        sweep_table(result.swept),
        f'### 틀린 질의 (hybrid, 거리 기준 {current:.2f})',
        '\n'.join(miss_lines(dataset, result)),
        '### 질의 하나를 벡터로 바꾸는 시간',
        latency_line(result.measurement),
    ]
    return '\n\n'.join(parts)


def summary_table(dataset: Dataset, results: list[ModelResult]) -> str:
    """모델들을 한눈에. 지금 기준의 hybrid F1, 가장 나은 기준과 그때의 F1, 벡터의 재현율@3, 시간."""
    rows = []
    for result in results:
        chosen = best(result.swept)
        rows.append(
            [
                result.measurement.model,
                ratio(f1(result.current.overall[Method.HYBRID])),
                f'{chosen.max_distance:.2f}',
                ratio(f1(chosen.overall[Method.HYBRID])),
                ratio(ranking_recall_at(result.measurement.ranked, dataset.queries, 3)),
                latency_line(result.measurement),
            ]
        )
    header = ['모델', 'F1(지금 기준)', '나은 기준', 'F1(나은 기준)', '벡터 재현율@3', '시간']
    return table(header, rows)


def full_report(dataset: Dataset, results: list[ModelResult]) -> str:
    """보고서 전체. 요약 표, 그리고 모델마다의 보고서."""
    head = f'# 로어북 검색 평가: {dataset.title} (항목 {len(dataset.entries)}개, 질의 {len(dataset.queries)}개)'
    return '\n\n'.join([head, summary_table(dataset, results), *(model_report(dataset, result) for result in results)])
