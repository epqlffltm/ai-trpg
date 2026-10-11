# game-server/evals/state/runner.py

"""
장면들을 실제 모델로 서술하게 하고 검사한다. 모델을 부르는 일(narrate)과 검사하는 일(inspect)을 나눈다.

서버와 같은 조립(app/rounds/prompt.py), 같은 생성 설정(NARRATION_PARAMS), 같은 장면 검사(accept_completion)를 거친다.
다시 시도와 다음 모델로 넘어가기는 하지 않는다. 한 번 부른 결과를 그대로 센다. 잘 쓰는지를 보는 도구라서다.
실패해도 예외를 올리지 않고 결과에 적는다. 한 장면이 실패해도 나머지는 돈다.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from app.ai.provider import Completion, LLMProvider, ProviderError, Reasoning
from app.rounds.llm_narrator import NARRATION_PARAMS, NarrationError, accept_completion
from app.rounds.prompt import build_messages
from evals.lore.narration import prompt_text
from evals.state.cases import CASES, StateCase
from evals.state.checks import Finding, general_hints, run_checks


@dataclass(frozen=True)
class Trial:
    """
    장면 하나를 한 번 서술하게 한 결과.

    scene 은 받은 장면, problem 은 provider 의 실패나 장면으로 받지 않은 이유다. 둘 중 하나만 있다.
    findings 는 장면의 검사 결과, hints 는 어느 장면에나 보는 의심거리다. 장면이 없으면 둘 다 비어 있다.
    """

    case: str
    model: str
    attempt: int
    seconds: float
    scene: str | None = None
    problem: str | None = None
    completion: Completion | None = None
    findings: tuple[Finding, ...] = ()
    hints: tuple[str, ...] = ()

    @property
    def broken(self) -> tuple[Finding, ...]:
        """걸린 검사들."""
        return tuple(finding for finding in self.findings if not finding.passed)


def inspect(trial: Trial, case: StateCase) -> Trial:
    """받은 장면을 검사해 결과에 적는다. 장면이 없으면 그대로 돌려준다."""
    if trial.scene is None:
        return trial
    prompt = prompt_text(build_messages(case.request))
    return replace(
        trial,
        findings=run_checks(trial.scene, case.checks),
        hints=tuple(general_hints(trial.scene, prompt)),
    )


async def narrate(provider: LLMProvider, case: StateCase, attempt: int, reasoning: Reasoning) -> Trial:
    """장면 하나를 한 번 서술하게 한다. 검사하지 않는다."""
    params = replace(NARRATION_PARAMS, reasoning=reasoning)
    started = time.perf_counter()
    base = {'case': case.name, 'model': provider.model, 'attempt': attempt}
    try:
        completion = await provider.complete(build_messages(case.request), params)
    except ProviderError as error:
        return Trial(**base, seconds=time.perf_counter() - started, problem=f'provider 실패: {error}')
    seconds = time.perf_counter() - started
    try:
        scene = accept_completion(completion)
    except NarrationError as error:
        return Trial(**base, seconds=seconds, completion=completion, problem=f'장면으로 받지 않음: {error}')
    return Trial(**base, seconds=seconds, completion=completion, scene=scene)


def rescore(trials: list[Trial]) -> list[Trial]:
    """다시 읽은 결과들을 지금의 검사로 다시 검사한다. 모델을 부르지 않는다."""
    by_name = {case.name: case for case in CASES}
    return [inspect(trial, by_name[trial.case]) for trial in trials]


async def run_cases(
    provider: LLMProvider,
    cases: tuple[StateCase, ...],
    repeat: int,
    reasoning: Reasoning = Reasoning.NONE,
    on_trial: Callable[[Trial], None] = lambda trial: None,
) -> list[Trial]:
    """장면마다 repeat 번 서술하게 하고 검사한다. 하나 끝날 때마다 on_trial 을 부른다(진행을 찍는 데 쓴다)."""
    trials = []
    for case in cases:
        for attempt in range(1, repeat + 1):
            trial = inspect(await narrate(provider, case, attempt, reasoning), case)
            on_trial(trial)
            trials.append(trial)
    return trials
