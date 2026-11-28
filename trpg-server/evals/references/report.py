# trpg-server/evals/references/report.py

"""
참고 자료 평가의 보고서(마크다운)를 만든다. 계산은 하지 않는다. runner 와 narration 이 낸 값을 표로 옮긴다.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from reference_core.selection import ReferenceThresholds

from evals.references.dataset import Dataset, SceneKind, SceneShape
from evals.references.narration import Mode, Trial, tally
from evals.references.runner import (
    TOP_KS,
    Measurement,
    Order,
    Outcome,
    Score,
    alias_distances,
    closest_answer,
    hit_at,
    score,
    score_by_kind,
    score_by_shape,
    spread,
    summary,
)

KIND_NAMES = {SceneKind.NAMED: '한국어로 부름', SceneKind.MEANING: '뜻으로만', SceneKind.NONE: '맞는 것 없음'}
SHAPE_NAMES = {SceneShape.ROUND: '라운드(trpg)', SceneShape.TALK: '대화(chat, story)'}
# 보고서의 머리말에 적는 자료의 이름
SOURCE_NAMES = {'srd51': 'SRD 5.1', 'wikipedia': '위키백과'}
# 넣는 차례의 이름
ORDER_NAMES = {
    Order.ALIAS_FIRST: '다른 이름 먼저',
    Order.BY_DISTANCE: '거리 순',
    Order.ALIAS_CAP: '다른 이름은 한 줄 덜(지금)',
}


@dataclass(frozen=True)
class ModelResult:
    """
    임베딩 모델 하나의 결과. current 는 지금 서버의 기준으로 고른 것, swept 는 거리 기준마다의 점수,
    keyword_swept 는 다른 이름의 상한마다의 점수, order_swept 는 넣는 차례와 거리 기준마다의 점수다
    (재지 않았으면 비어 있다).
    """

    measurement: Measurement
    current: list[Outcome]
    swept: list[tuple[float, Score]]
    keyword_swept: list[tuple[float, Score]] = field(default_factory=list)
    order_swept: list[tuple[Order, float, Score]] = field(default_factory=list)


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


def sources_line(dataset: Dataset) -> str:
    """자료의 줄을 자료마다 센 것. "SRD 5.1 810줄, 위키백과 194줄" 이다."""
    counts: dict[str, int] = {}
    for reference in dataset.references:
        counts[reference.source] = counts.get(reference.source, 0) + 1
    return ', '.join(f'{SOURCE_NAMES.get(source, source)} {count}줄' for source, count in counts.items())


def limit_label(distance: float) -> str:
    """다른 이름의 상한. 상한이 없으면 '없음' 이다."""
    return '없음' if math.isinf(distance) else f'{distance:.2f}'


def keyword_lines(result: ModelResult, thresholds: ReferenceThresholds) -> list[str]:
    """다른 이름의 상한을 바꿔 가며 매긴 표. 재지 않았으면 빈 목록이다."""
    if not result.keyword_swept:
        return []
    lines = [
        '',
        f'**다른 이름의 상한을 바꿔 가며**(거리 기준은 {thresholds.max_distance} 그대로)',
        '',
        '| 다른 이름 | 맞힘 | 정밀도 | 비우기 | 장면마다 고른 수 |',
        '| --- | --- | --- | --- | --- |',
    ]
    lines.extend(score_row(limit_label(distance), swept) for distance, swept in result.keyword_swept)
    return lines


def order_lines(result: ModelResult, thresholds: ReferenceThresholds) -> list[str]:
    """넣는 차례와 거리 기준을 함께 바꿔 가며 매긴 표. 재지 않았으면 빈 목록이다."""
    if not result.order_swept:
        return []
    lines = [
        '',
        f'**넣는 차례를 바꿔 가며**(다른 이름의 상한 {thresholds.keyword_max_distance}, {thresholds.limit}줄)',
        '',
        '| 차례 | 거리 | 맞힘 | 정밀도 | 비우기 | 장면마다 고른 수 |',
        '| --- | --- | --- | --- | --- | --- |',
    ]
    for order, distance, swept in result.order_swept:
        row = score_row(f'{ORDER_NAMES[order]} | {distance:.2f}', swept)
        lines.append(row)
    return lines


def closest_cell(dataset: Dataset, outcome: Outcome, measurement: Measurement) -> str:
    """장면에서 가장 가까운 정답의 key, 거리, 모든 줄 가운데의 차례. 정답이 없는 장면은 '-' 다."""
    closest = closest_answer(outcome.scene, dataset, measurement)
    if closest is None:
        return '-'
    return f'{closest.key} {closest.distance:.3f} ({closest.rank}번째)'


def aliased_cell(dataset: Dataset, outcome: Outcome, measurement: Measurement, limit: float) -> str:
    """장면에서 다른 이름으로 걸린 줄과 거리. 상한보다 멀어 뺀 것에 (뺌)을 붙인다. 없으면 '(없음)' 이다."""
    found = alias_distances(outcome.scene, dataset, measurement)
    if not found:
        return '(없음)'
    cells = []
    for key, distance in found:
        if distance is None:
            cells.append(f'{key} -')
        else:
            cells.append(f'{key} {distance:.3f}' + (' (뺌)' if distance > limit else ''))
    return ', '.join(cells)


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
        f'## {measurement.label}',
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
    lines.extend(
        score_row(SHAPE_NAMES[shape], shape_score) for shape, shape_score in score_by_shape(result.current).items()
    )
    lines.extend(['', '**거리 기준을 바꿔 가며**', '', '| 거리 | 맞힘 | 정밀도 | 비우기 | 장면마다 고른 수 |'])
    lines.append('| --- | --- | --- | --- | --- |')
    chosen = best(result.swept)
    for distance, swept in result.swept:
        mark = ' (가장 나음)' if distance == chosen else ''
        lines.append(score_row(f'{distance:.2f}{mark}', swept))
    lines.extend(keyword_lines(result, thresholds))
    lines.extend(order_lines(result, thresholds))
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
            '| 장면 | 종류 | 정답 | 고른 것 | 가장 가까운 정답(거리, 차례) | 다른 이름으로 걸린 것(거리) |',
            '| --- | --- | --- | --- | --- | --- |',
        ]
    )
    for outcome in result.current:
        mark = 'O' if outcome.hit else ('-' if not outcome.scene.expected else 'X')
        expected = ', '.join(sorted(outcome.scene.expected)) or '(없음)'
        chosen_keys = ', '.join(outcome.chosen) or '(없음)'
        aliased = aliased_cell(dataset, outcome, measurement, thresholds.keyword_max_distance)
        kind = KIND_NAMES[outcome.scene.kind] + (' · 대화' if outcome.scene.shape == SceneShape.TALK else '')
        closest = closest_cell(dataset, outcome, measurement)
        lines.append(f'| {outcome.scene.name} {mark} | {kind} | {expected} | {chosen_keys} | {closest} | {aliased} |')
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
        f'장면 {len(dataset.scenes)}개(evals/references/scenes.yaml), '
        f'자료 {len(dataset.references)}줄({sources_line(dataset)}).',
        '자료의 벡터 글은 서버와 같다. 생김새 글이 있으면 이름과 생김새 글, 없으면 이름, 다른 이름, 글이다'
        '(reference_core/texts.py). 다른 글로 잰 절은 머리에 그 글을 적는다.',
        '찾는 글도 서버와 같다. 라운드(trpg)는 장면과 선언들, 대화(chat, story)는 마지막 두 말이다.',
        '한국어 이름이 장면에 나오면 다른 이름으로도 고른다. 그 줄도 다른 이름의 상한보다 멀면 뺀다(동음이의어).',
        '',
    ]
    for result in results:
        lines.extend(model_section(dataset, result, thresholds))
    lines.extend(narration_section(trials))
    return '\n'.join(lines).rstrip() + '\n'
