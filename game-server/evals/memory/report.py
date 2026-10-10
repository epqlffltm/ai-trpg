# game-server/evals/memory/report.py

"""
지난 일 검색의 평가 결과를 마크다운으로 만든다. 순수한 함수다. 콘솔에 찍고, --out 이면 파일로도 남긴다.

모델 하나의 보고서.
  1. 지금 서버의 기준(MEMORY_MAX_DISTANCE, MEMORY_KEYWORD_MAX_DISTANCE 의 기본값)으로 매긴 점수, 종류별 점수, 틀린 질의
  2. 정답인 기억과 그 밖의 기억의 거리 분포. 둘이 갈리는 곳이 거리 기준의 후보다
  3. 기준을 바꿔 가며 매긴 것 중 F1 이 높은 것들과, 가장 나은 기준
  4. 가장 나은 기준에서 틀린 질의(무엇을 놓쳤고 무엇을 잘못 넣었나)
"""

import math
from dataclasses import dataclass

from app.memory.retrieval import MemoryThresholds
from evals.lore.dataset import Kind
from evals.lore.metrics import five_numbers
from evals.lore.report import ratio, table
from evals.memory.dataset import MemoryDataset
from evals.memory.runner import Evaluation, Measurement, best, split_distances

# 기준을 바꿔 가며 매긴 것 중 보여 줄 수
TOP = 10


@dataclass(frozen=True)
class ModelResult:
    """모델 하나의 결과. 지금 기준으로 매긴 것과, 기준을 바꿔 가며 매긴 것."""

    measurement: Measurement
    current: Evaluation
    swept: list[Evaluation]


def gate_label(value: float) -> str:
    """인물의 상한. 없으면 '없음'."""
    return '없음' if math.isinf(value) else f'{value:.2f}'


def rule_label(thresholds: MemoryThresholds) -> str:
    """기준 한 줄."""
    return f'거리 {thresholds.max_distance:.2f}, 인물 상한 {gate_label(thresholds.keyword_max_distance)}'


def score_table(evaluation: Evaluation) -> str:
    """전체와 종류별 점수."""
    rows = [['전체', *score_cells(evaluation.overall), str(evaluation.overall.queries)]]
    for kind in Kind:
        if kind in evaluation.by_kind:
            kind_score = evaluation.by_kind[kind]
            rows.append([kind.value, *score_cells(kind_score), str(kind_score.queries)])
    return table(['질의', '재현율', '정밀도', 'MRR', '비움', '수'], rows)


def score_cells(score_) -> list[str]:
    return [ratio(score_.recall), ratio(score_.precision), ratio(score_.mrr), ratio(score_.empty)]


def distance_table(dataset: MemoryDataset, measurement: Measurement) -> str:
    """정답인 기억과 그 밖의 기억의 거리 분포(최소, 25%, 중앙, 75%, 최대)."""
    right, other = split_distances(dataset, measurement)
    rows = []
    for label, values in (('정답', right), ('그 밖', other)):
        numbers = five_numbers(values)
        cells = ['-'] * 5 if numbers is None else [f'{value:.2f}' for value in numbers]
        rows.append([label, *cells, str(len(values))])
    return table(['기억', '최소', '25%', '중앙', '75%', '최대', '수'], rows)


def sweep_table(swept: list[Evaluation]) -> str:
    """F1 이 높은 기준들."""
    ranked = sorted(swept, key=lambda item: (item.f1, item.overall.recall or 0.0), reverse=True)[:TOP]
    rows = [
        [
            f'{item.thresholds.max_distance:.2f}',
            gate_label(item.thresholds.keyword_max_distance),
            f'{item.f1:.2f}',
            ratio(item.overall.recall),
            ratio(item.overall.precision),
            ratio(item.overall.empty),
        ]
        for item in ranked
    ]
    return table(['거리', '인물 상한', 'F1', '재현율', '정밀도', '비움'], rows)


def miss_lines(evaluation: Evaluation) -> list[str]:
    """틀린 질의마다 한 줄. 정답과 고른 것이 같으면 뺀다."""
    lines = []
    for outcome in evaluation.outcomes:
        expected = sorted(outcome.query.expected, key=int)
        if set(outcome.chosen) == set(expected):
            continue
        lines.append(
            f'- {outcome.query.id}({outcome.query.kind.value}, {outcome.query.request.round_number} 라운드): '
            f'정답 {", ".join(expected) or "없음"} / 고름 {", ".join(outcome.chosen) or "없음"}'
        )
    return lines or ['- 없음']


def model_report(dataset: MemoryDataset, result: ModelResult) -> str:
    """모델 하나의 보고서."""
    chosen = best(result.swept)
    parts = [
        f'## {result.measurement.model}',
        f'### 지금 서버의 기준({rule_label(result.current.thresholds)}), F1 {result.current.f1:.2f}',
        score_table(result.current),
        '#### 지금 기준에서 틀린 질의',
        '\n'.join(miss_lines(result.current)),
        '### 거리 분포(고를 수 있는 기억만)',
        distance_table(dataset, result.measurement),
        f'### 기준을 바꿔 가며(위 {TOP}개)',
        sweep_table(result.swept),
        f'가장 나은 기준: {rule_label(chosen.thresholds)}, F1 {chosen.f1:.2f}',
        '### 가장 나은 기준에서 틀린 질의',
        '\n'.join(miss_lines(chosen)),
    ]
    return '\n\n'.join(parts)


def full_report(dataset: MemoryDataset, results: list[ModelResult]) -> str:
    """모든 모델의 보고서."""
    head = f'# 지난 일 검색 평가: {dataset.title}\n\n기억 {len(dataset.memories)}개, 질의 {len(dataset.queries)}개'
    return '\n\n'.join([head, *(model_report(dataset, result) for result in results)]) + '\n'
