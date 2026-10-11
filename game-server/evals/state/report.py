# game-server/evals/state/report.py

"""
상태 지키기 평가의 결과를 마크다운으로 만든다. 순수한 함수다. 콘솔에 찍고, --out 이면 파일로도 남긴다.

  1. 한눈에 보는 표. 모델과 장면마다, 검사마다 몇 번 중 몇 번 걸렸나. 실패(장면을 못 받음)도 센다
  2. 장면마다의 글. 걸린 검사와 근거, 의심거리를 장면 위에 적는다. 사람이 읽고 판단한다

남긴 보고서를 다시 읽을 수도 있다(read_report). 검사의 낱말을 고친 뒤 모델을 다시 부르지 않고 다시 셀 때 쓴다.
"""

import re
from collections.abc import Sequence

from evals.state.cases import CASES, StateCase
from evals.state.runner import Trial


def find_case(name: str) -> StateCase:
    """이름으로 장면을 찾는다. 결과는 늘 아는 장면에서 나온다."""
    return next(case for case in CASES if case.name == name)


def group_by(trials: Sequence[Trial]) -> dict[tuple[str, str], list[Trial]]:
    """모델과 장면으로 묶는다. 돌린 차례대로."""
    groups: dict[tuple[str, str], list[Trial]] = {}
    for trial in trials:
        groups.setdefault((trial.model, trial.case), []).append(trial)
    return groups


def count_cell(group: Sequence[Trial], label: str) -> str:
    """장면을 받은 것 중 그 검사에 걸린 수. '걸림/받음'."""
    scenes = [trial for trial in group if trial.scene is not None]
    caught = sum(any(finding.label == label for finding in trial.broken) for trial in scenes)
    return f'{caught}/{len(scenes)}'


def tally_lines(trials: Sequence[Trial]) -> list[str]:
    """모델과 장면마다 한 줄. 검사의 이름과 걸린 수를 적는다. 장면마다 검사가 달라서 칸을 고정하지 않는다."""
    lines = ['| 모델 | 장면 | 횟수 | 실패 | 검사(걸림/받음) |', '| --- | --- | --- | --- | --- |']
    for (model, name), group in group_by(trials).items():
        checks = ', '.join(f'{check.label} {count_cell(group, check.label)}' for check in find_case(name).checks)
        failures = sum(trial.scene is None for trial in group)
        lines.append(f'| {model} | {name} | {len(group)} | {failures} | {checks} |')
    return lines


def total_line(trials: Sequence[Trial]) -> str:
    """전체에서 걸린 장면의 수. 검사 하나라도 걸린 장면을 센다."""
    scenes = [trial for trial in trials if trial.scene is not None]
    caught = sum(bool(trial.broken) for trial in scenes)
    return f'받은 장면 {len(scenes)}개 중 검사에 걸린 장면 {caught}개, 실패 {len(trials) - len(scenes)}개'


def describe(trial: Trial) -> str:
    """결과 하나를 읽기 좋은 글로. 걸린 검사와 근거를 장면 위에 적는다."""
    case = find_case(trial.case)
    lines = [f'## {trial.case} #{trial.attempt} / {trial.model} / {trial.seconds:.1f}초', case.about]
    if trial.completion is not None:
        completion = trial.completion
        lines.append(f'토큰: 입력 {completion.input_tokens}, 출력 {completion.output_tokens}')
    if trial.problem is not None:
        lines.append(trial.problem)
    for finding in trial.broken:
        lines.append(f'- 걸림: {finding.label}({", ".join(finding.evidence)})')
    if trial.hints:
        lines.append(f'- 확인할 것: {", ".join(trial.hints)}')
    if trial.scene is not None:
        lines.extend(['', trial.scene])
    lines.append('')
    return '\n'.join(lines)


# 장면 하나의 머리 줄. "## 장면 #번호 / 모델 / 1.7초"
HEAD = re.compile(r'^(?P<case>\S+) #(?P<attempt>\d+) / (?P<model>.+) / (?P<seconds>[\d.]+)초$')


def read_trial(part: str) -> Trial:
    """
    보고서의 장면 하나("## " 뒤)를 다시 읽는다. 장면은 머리 줄들 뒤의 첫 빈 줄부터 끝까지다.

    검사의 결과는 읽지 않는다. 다시 셀 것이라서다. 장면이 없던 것(실패)은 무엇이 실패였는지 모른 채 남긴다.
    """
    head, _, rest = part.partition('\n')
    found = HEAD.match(head.strip())
    if found is None:
        raise ValueError(f'장면의 머리 줄이 아니다: {head}')
    _, _, scene = rest.partition('\n\n')
    scene = scene.strip()
    base = {
        'case': found['case'],
        'model': found['model'],
        'attempt': int(found['attempt']),
        'seconds': float(found['seconds']),
    }
    if not scene:
        return Trial(**base, problem='다시 읽음: 장면 없음')
    return Trial(**base, scene=scene)


def read_report(text: str) -> list[Trial]:
    """남긴 보고서(full_report)의 장면들을 다시 읽는다. 맨 앞의 표는 건너뛴다."""
    return [read_trial(part) for part in re.split(r'^## ', text, flags=re.MULTILINE)[1:]]


def full_report(trials: Sequence[Trial]) -> str:
    """표, 전체 한 줄, 장면 전부."""
    return '\n'.join([*tally_lines(trials), '', total_line(trials), '', *(describe(trial) for trial in trials)])
