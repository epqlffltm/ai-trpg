# trpg-server/evals/references/report.py

"""
참고 자료 평가의 보고서(마크다운)를 만든다. 계산은 하지 않는다. runner 와 narration 이 낸 값을 표로 옮긴다.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.references.retrieval import ReferenceThresholds
from evals.references.dataset import Dataset, SceneKind
from evals.references.narration import Mode, Trial, tally
from evals.references.runner import (
    TOP_KS,
    Measurement,
    Outcome,
    Score,
    hit_at,
    score,
    score_by_kind,
    spread,
    summary,
)

KIND_NAMES = {SceneKind.NAMED: '한국어로 부름', SceneKind.MEANING: '뜻으로만', SceneKind.NONE: '맞는 것 없음'}


@dataclass(frozen=True)
class ModelResult:
    """임베딩 모델 하나의 결과. current 는 지금 서버의 기준으로 고른 것, swept 는 거리 기준마다의 점수다."""

    measurement: Measurement
    current: list[Outcome]
    swept: list[tuple[float, Score]]


def percent(value: float | None) -> str:
    """비율을 백분율로. 없으면 '-' 다."""
    return '-' if value is None else f'{value * 100:.0f}%'


def number(value: float | None) -> str:
    """수를 반올림해서. 없으면 '-' 다."""
    return '-' if value is None else f'{value:.0f}'


def best(swept: Sequence[tuple[float, Score]]) -> float:
    """맞힘과 비우기의 평균이 가장 높은 거리 기준. 같으면 작은 것(덜 넣는 쪽)이다."""

    def merit(item: tuple[float, Score]) -> float:
        _, result = item
        return ((result.hit or 0) + (result.empty or 0)) / 2

    return max(swept, key=lambda item: (merit(item), -item[0]))[0]


def score_row(label: str, result: Score) -> str:
    """점수 한 줄."""
    return (
        f'| {label} | {percent(result.hit)} | {percent(result.precision)} | {percent(result.empty)} '
        f'| {result.chosen_per_scene:.1f} |'
    )


def model_section(dataset: Dataset, result: ModelResult, thresholds: ReferenceThresholds) -> list[str]:
    """임베딩 모델 하나의 절."""
    measurement = result.measurement
    distances = spread(dataset, measurement)
    lines = [
        f'## {measurement.model}',
        '',
        f'자료 {len(dataset.references)}줄과 장면 {len(dataset.scenes)}개를 벡터로 바꾸는 데 '
        f'{measurement.seconds:.1f}초.',
        '',
        f'**지금 서버의 기준**(거리 {thresholds.max_distance}, 다른 이름 {thresholds.keyword_max_distance}, '
        f'{thresholds.limit}줄, {thresholds.max_chars}자)',
        '',
        '| 장면 | 맞힘 | 정밀도 | 비우기 | 장면마다 고른 수 |',
        '| --- | --- | --- | --- | --- |',
        score_row('전체', score(result.current)),
    ]
    lines.extend(score_row(KIND_NAMES[kind], kind_score) for kind, kind_score in score_by_kind(result.current).items())
    lines.extend(['', '**거리 기준을 바꿔 가며**', '', '| 거리 | 맞힘 | 정밀도 | 비우기 | 장면마다 고른 수 |'])
    lines.append('| --- | --- | --- | --- | --- |')
    chosen = best(result.swept)
    for distance, swept in result.swept:
        mark = ' (가장 나음)' if distance == chosen else ''
        lines.append(score_row(f'{distance:.2f}{mark}', swept))
    hits = ', '.join(f'@{k} {percent(hit_at(dataset, measurement, k))}' for k in TOP_KS)
    lines.extend(
        [
            '',
            f'**거리 기준 없이 가까운 순**: {hits}',
            '',
            '**거리(최소 / 중앙 / 최대)**',
            f'- 장면마다 가장 가까운 정답: {summary(distances.expected)}',
            f'- 장면마다 정답이 아닌 가장 가까운 줄: {summary(distances.others)}',
            '',
            '**장면마다 고른 것(지금 기준)**',
            '',
            '| 장면 | 종류 | 정답 | 고른 것 |',
            '| --- | --- | --- | --- |',
        ]
    )
    for outcome in result.current:
        mark = 'O' if outcome.hit else ('-' if not outcome.scene.expected else 'X')
        expected = ', '.join(sorted(outcome.scene.expected)) or '(없음)'
        chosen_keys = ', '.join(outcome.chosen) or '(없음)'
        lines.append(f'| {outcome.scene.name} {mark} | {KIND_NAMES[outcome.scene.kind]} | {expected} | {chosen_keys} |')
    lines.append('')
    return lines


def narration_section(trials: Sequence[Trial]) -> list[str]:
    """켠 서술과 끈 서술을 견준 절. 서술하지 않았으면 빈 목록이다."""
    if not trials:
        return []
    lines = [
        '## 켠 서술과 끈 서술',
        '',
        '| 방식 | 서술 | 실패 | 수치가 샌 서술 | 입력 토큰(평균) | 출력 토큰(평균) | 글자 수(평균) |',
        '| --- | --- | --- | --- | --- | --- | --- |',
    ]
    for mode in Mode:
        counted = tally(trials, mode)
        lines.append(
            f'| {mode} | {counted.runs} | {counted.failed} | {counted.leaked} | {number(counted.mean_input_tokens)} '
            f'| {number(counted.mean_output_tokens)} | {number(counted.mean_chars)} |'
        )
    lines.extend(['', '서술이 나아졌는지는 아래의 장면을 읽고 판단한다.', ''])
    for trial in trials:
        lines.append(f'### {trial.scene_name} · {trial.mode} · {trial.attempt}회 · {trial.model}')
        if trial.references:
            lines.append(f'넣은 참고 자료: {", ".join(trial.references)}')
        if trial.leaked:
            lines.append(f'**수치가 샜다**: {", ".join(trial.leaked)}')
        lines.extend(['', trial.text if trial.text is not None else f'(실패: {trial.error})', ''])
    return lines


def full_report(
    dataset: Dataset, results: Sequence[ModelResult], thresholds: ReferenceThresholds, trials: Sequence[Trial] = ()
) -> str:
    """보고서 전체."""
    lines = [
        '# 참고 자료 평가',
        '',
        f'장면 {len(dataset.scenes)}개(evals/references/scenes.yaml), 자료 {len(dataset.references)}줄(SRD 5.1).',
        '자료가 영어라 한국어 장면과의 거리를 잰다. 다른 이름(한국어 이름)이 비어 있으면 벡터로만 고른다.',
        '',
    ]
    for result in results:
        lines.extend(model_section(dataset, result, thresholds))
    lines.extend(narration_section(trials))
    return '\n'.join(lines).rstrip() + '\n'
