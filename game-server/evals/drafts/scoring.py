# game-server/evals/drafts/scoring.py

"""
초안 한 번을 정답과 견주고, 여러 번을 모아 센다. 순수 함수다.

센 것.
  - 읽었나: 답이 JSON 이고 모양이 맞았나(구조화 출력의 성공률). 아니면 그 까닭(not_json, bad_shape, cut_off …).
  - 맞았나: 서버가 받은 초안이 정답과 똑같은가.
  - 더한 것: 정답에 없는데 받은 초안(방장이 버려야 하는 것).
  - 놓친 것: 정답에 있는데 없는 초안.
  - 지어낸 것: 서버가 버린 초안(없는 이름표, 바꿀 수 없는 퀘스트, 겹친 것).
"""

from dataclasses import dataclass

from app.ai.calls import Outcome
from app.drafts.validation import Checked
from evals.drafts.cases import DraftCase


@dataclass(frozen=True)
class DraftTrial:
    """장면 하나를 한 모델로 한 번 돌린 결과."""

    model: str
    case: str
    seconds: float
    outcome: Outcome
    error: str | None
    items: frozenset[tuple[str, str, int]]
    quests: frozenset[tuple[str, str]]
    rejected: int
    extra: int
    missed: int
    text: str | None

    @property
    def read(self) -> bool:
        """답을 초안으로 읽었는가."""
        return self.outcome == Outcome.OK

    @property
    def exact(self) -> bool:
        """읽었고, 받은 초안이 정답과 똑같은가."""
        return self.read and self.extra == 0 and self.missed == 0


def drafted(checked: Checked) -> tuple[frozenset[tuple[str, str, int]], frozenset[tuple[str, str]]]:
    """서버가 받은 초안을 정답과 같은 모양(이름)으로."""
    items = frozenset((item.character_name, item.name, item.count) for item in checked.items)
    quests = frozenset((quest.name, str(quest.status)) for quest in checked.quests)
    return items, quests


def score(
    model: str,
    case: DraftCase,
    seconds: float,
    checked: Checked,
    outcome: Outcome,
    error: str | None,
    text: str | None,
) -> DraftTrial:
    """한 번의 결과를 정답과 견준다. 읽지 못했으면 받은 것이 없으니 정답 전부를 놓친 것이다."""
    items, quests = drafted(checked)
    extra = len(items - case.items) + len(quests - case.quests)
    missed = len(case.items - items) + len(case.quests - quests)
    return DraftTrial(
        model, case.name, seconds, outcome, error, items, quests, len(checked.rejected), extra, missed, text
    )


@dataclass(frozen=True)
class ModelSummary:
    """한 모델의 시도들을 모은 것."""

    model: str
    trials: int
    read: int
    exact: int
    extra: int
    missed: int
    rejected: int
    seconds: float


def summarize(trials: list[DraftTrial]) -> list[ModelSummary]:
    """모델마다 센다. 모델이 처음 나온 순서다."""
    models = list(dict.fromkeys(trial.model for trial in trials))
    summaries = []
    for model in models:
        mine = [trial for trial in trials if trial.model == model]
        summaries.append(
            ModelSummary(
                model=model,
                trials=len(mine),
                read=sum(trial.read for trial in mine),
                exact=sum(trial.exact for trial in mine),
                extra=sum(trial.extra for trial in mine),
                missed=sum(trial.missed for trial in mine),
                rejected=sum(trial.rejected for trial in mine),
                seconds=sum(trial.seconds for trial in mine) / len(mine),
            )
        )
    return summaries


def summary_table(summaries: list[ModelSummary]) -> list[str]:
    """모은 것을 마크다운 표로."""
    lines = [
        '| 모델 | 시도 | 읽음 | 정답 | 더한 것 | 놓친 것 | 지어낸 것 | 평균 초 |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for row in summaries:
        lines.append(
            f'| {row.model} | {row.trials} | {row.read} | {row.exact} | {row.extra} | {row.missed} '
            f'| {row.rejected} | {row.seconds:.1f} |'
        )
    return lines


def case_table(trials: list[DraftTrial]) -> list[str]:
    """장면마다 정답을 맞힌 횟수. 모델과 장면의 순서다."""
    lines = ['| 모델 | 장면 | 정답 / 시도 | 읽지 못함 |', '| --- | --- | --- | --- |']
    keys = list(dict.fromkeys((trial.model, trial.case) for trial in trials))
    for model, case in keys:
        mine = [trial for trial in trials if (trial.model, trial.case) == (model, case)]
        failed = ', '.join(sorted({trial.error for trial in mine if not trial.read and trial.error})) or '-'
        lines.append(f'| {model} | {case} | {sum(trial.exact for trial in mine)} / {len(mine)} | {failed} |')
    return lines
