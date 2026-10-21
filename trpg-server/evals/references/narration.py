# trpg-server/evals/references/narration.py

"""
참고 자료를 켠 서술과 끈 서술을 견준다(#482 3단계). scripts/eval_references.py 의 --narrate 가 쓴다.

같은 장면을 둘로 서술하게 한다.
  - off: 참고 자료를 넣지 않는다(지금의 기본)
  - on:  서버의 규칙과 같은 임베딩 모델로 고른 줄을 넣는다(evals/references/runner.py 의 pick_for)
서버의 서술자(LLMNarrator)를 그대로 쓴다. 예산에 맞게 줄이는 것(app/rounds/budget.py)도 같다.

재는 것.
  - 늘어난 입력 토큰. provider 가 알려 준 만큼이다(모르면 비어 있다). 판매가가 가정한 입력(12,000) 안인지 본다.
  - 수치가 샌 서술. 참고 자료의 글에는 수치가 없지만 모델이 원본의 규칙을 떠올려 쓸 수 있다(DC 14, 2d6, +5).
  - 장면의 길이.
서술이 나아졌는지(생김새와 쓰임을 더 그럴듯하게 그렸는지)는 사람이 보고서의 장면을 읽고 판단한다.
"""

import enum
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from ai_core.fake import FakeCallLog
from ai_core.provider import LLMProvider, ProviderError

from app.references.retrieval import ReferenceThresholds, to_reference_note
from app.rounds.llm_narrator import LLMNarrator, NarrationError
from app.rounds.narrator import ReferenceNote
from evals.references.dataset import Dataset, Scene
from evals.references.runner import Measurement, pick_for

# 서술에 나오면 안 되는 판정의 수치. 참고 자료의 글을 거르는 것(app/references/srd.py)과 같은 뜻이다
LEAKED_NUMBERS = re.compile(
    r'\bDC\s*\d+|\b\d*d\d+\b|[+-]\d+\b|난이도\s*\d+|명중\s*[+-]?\d+|면체 주사위|\d+\s*[이가]\s*나오면', re.IGNORECASE
)


class Mode(enum.StrEnum):
    """서술에 참고 자료를 넣는가."""

    OFF = 'off'
    ON = 'on'


@dataclass(frozen=True)
class Trial:
    """한 번의 서술. scene 은 서술한 글(실패했으면 None), error 는 실패한 까닭이다."""

    scene_name: str
    model: str
    mode: Mode
    attempt: int
    references: list[str]
    text: str | None
    error: str | None
    input_tokens: int | None
    output_tokens: int | None

    @property
    def leaked(self) -> list[str]:
        """서술에 나온 판정의 수치들. 없으면 빈 목록이다."""
        return LEAKED_NUMBERS.findall(self.text or '')


def references_for(
    scene: Scene, dataset: Dataset, measurement: Measurement, thresholds: ReferenceThresholds
) -> list[ReferenceNote]:
    """장면에 넣을 참고 자료. 서버의 규칙으로 고른 것이다."""
    distances = measurement.distances[scene.name]
    return [to_reference_note(reference) for reference in pick_for(scene, dataset.references, distances, thresholds)]


async def narrate_once(
    provider: LLMProvider, scene: Scene, notes: Sequence[ReferenceNote], mode: Mode, attempt: int
) -> Trial:
    """한 번 서술하게 한다. off 면 참고 자료를 넣지 않는다. 실패해도 예외를 올리지 않고 Trial 에 까닭을 적는다."""
    log = FakeCallLog()
    sent = list(notes) if mode == Mode.ON else []
    request = replace(scene.request, references=sent)
    text, error = None, None
    try:
        text = await LLMNarrator(provider, log).narrate(request)
    except (NarrationError, ProviderError) as failure:
        error = str(failure)
    record = log.records[-1] if log.records else None
    return Trial(
        scene_name=scene.name,
        model=provider.model,
        mode=mode,
        attempt=attempt,
        references=[note.name for note in sent],
        text=text,
        error=error,
        input_tokens=record.input_tokens if record else None,
        output_tokens=record.output_tokens if record else None,
    )


async def run_pairs(
    provider: LLMProvider,
    dataset: Dataset,
    measurement: Measurement,
    thresholds: ReferenceThresholds,
    repeat: int,
    on_trial=None,
) -> list[Trial]:
    """
    장면마다 off 와 on 을 repeat 번씩 서술하게 한다. 참고 자료를 고르지 못한 장면(정답이 없는 장면 등)도 돈다.

    on_trial 은 하나 끝날 때마다 부르는 함수다(오래 도는 동안 멈춘 것이 아님을 보인다).
    """
    trials = []
    for scene in dataset.scenes:
        notes = references_for(scene, dataset, measurement, thresholds)
        for attempt in range(1, repeat + 1):
            for mode in Mode:
                trial = await narrate_once(provider, scene, notes, mode, attempt)
                trials.append(trial)
                if on_trial is not None:
                    on_trial(trial)
    return trials


@dataclass(frozen=True)
class Tally:
    """한 방식(off, on)의 합계. 평균은 알려진 값만으로 낸다. 없으면 None 이다."""

    mode: Mode
    runs: int
    failed: int
    leaked: int
    mean_input_tokens: float | None
    mean_output_tokens: float | None
    mean_chars: float | None


def mean(values: Sequence[float]) -> float | None:
    """평균. 값이 없으면 None 이다."""
    return sum(values) / len(values) if values else None


def tally(trials: Sequence[Trial], mode: Mode) -> Tally:
    """한 방식의 합계."""
    chosen = [trial for trial in trials if trial.mode == mode]
    done = [trial for trial in chosen if trial.text is not None]
    return Tally(
        mode=mode,
        runs=len(chosen),
        failed=len(chosen) - len(done),
        leaked=sum(1 for trial in done if trial.leaked),
        mean_input_tokens=mean([trial.input_tokens for trial in done if trial.input_tokens is not None]),
        mean_output_tokens=mean([trial.output_tokens for trial in done if trial.output_tokens is not None]),
        mean_chars=mean([len(trial.text) for trial in done]),
    )
