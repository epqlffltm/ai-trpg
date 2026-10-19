# trpg-server/tests/test_retry_budget.py

"""
재시도 예산(app/ai/retry_budget.py)과 그것을 쓰는 다시 시도하는 서술자(app/rounds/retrying_narrator.py)를 검증한다.

보는 것.
  - 비율: 최근 창 안의 첫 시도 수의 10% 까지만 다시 부른다. 손님이 적어도 3 번은 늘 된다.
  - 창: 창 밖으로 나간 시도는 세지 않는다.
  - 모델마다 따로 센다.
  - 서술자: 예산이 없으면 같은 모델로 다시 부르지 않고 그 실패로 끝낸다. 예산을 앱이 함께 쓴다.
"""

from dataclasses import dataclass, field

import pytest

from app.ai.provider import ProviderError
from app.ai.retry_budget import FLOOR, RATIO, WINDOW_SECONDS, RetryBudget, allowance
from app.rounds.narrator import NO_PREVIEW, Move, NarrationRequest, Preview, StoryContext
from app.rounds.retrying_narrator import NarrationFailed, RetryingNarrator

REQUEST = NarrationRequest(
    round_number=1,
    scene='사이렌이 울린다.',
    moves=[Move('엘프', '달린다.')],
    story=StoryContext(title='추격전', rating='all', guide=''),
)
SCENE = '엔진 소리가 골목을 메운다.'


@dataclass
class Clock:
    """테스트가 돌리는 시계."""

    now: float = 0.0

    def __call__(self) -> float:
        return self.now


def budget(clock: Clock) -> RetryBudget:
    return RetryBudget(clock=clock)


# --- 예산 ---


@pytest.mark.parametrize(('requests', 'allowed'), [(0, FLOOR), (10, FLOOR), (30, FLOOR), (40, 4), (100, 10)])
def test_the_allowance_is_a_tenth_of_the_requests_but_never_below_the_floor(requests: int, allowed: int):
    assert allowance(requests, RATIO, FLOOR) == allowed


def test_a_few_retries_are_always_allowed():
    retries = budget(Clock())
    retries.note_request('gpt-6-luna')

    # 첫 시도가 하나뿐이어도 한 번의 실패로 막히지 않는다
    assert [retries.try_retry('gpt-6-luna') for _ in range(FLOOR + 1)] == [True] * FLOOR + [False]


def test_many_requests_buy_more_retries():
    retries = budget(Clock())
    for _ in range(50):
        retries.note_request('gpt-6-luna')

    # 50 의 10% 는 5 번이다
    assert sum(retries.try_retry('gpt-6-luna') for _ in range(10)) == 5


def test_retries_outside_the_window_are_forgotten():
    clock = Clock()
    retries = budget(clock)
    retries.note_request('gpt-6-luna')
    for _ in range(FLOOR):
        retries.try_retry('gpt-6-luna')

    clock.now = WINDOW_SECONDS + 1

    assert retries.try_retry('gpt-6-luna') is True


def test_each_model_has_its_own_budget():
    retries = budget(Clock())
    for _ in range(FLOOR):
        retries.try_retry('gpt-6-luna')

    # 한 모델이 아파 예산을 다 써도 다른 모델은 다시 부를 수 있다
    assert retries.try_retry('gpt-6-luna') is False
    assert retries.try_retry('claude-sonnet-5-5') is True


# --- 서술자 ---


@dataclass
class Model:
    """정해 둔 대로 하는 모델의 서술자. model 이 재시도 예산의 이름이다."""

    model: str
    outcomes: list
    calls: list[str] = field(default_factory=list)

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.calls.append(self.model)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


async def no_sleep(seconds: float) -> None:
    return None


def chain(model: Model, retries: RetryBudget | None) -> RetryingNarrator:
    return RetryingNarrator([model], attempt_timeout=60.0, pause=lambda: 1.0, sleep=no_sleep, retry_budget=retries)


async def test_with_budget_left_the_model_is_called_again():
    model = Model('gpt-6-luna', [ProviderError('status_503'), SCENE])

    assert await chain(model, budget(Clock())).narrate(REQUEST) == SCENE
    assert len(model.calls) == 2


async def test_without_budget_the_model_is_not_called_again():
    retries = budget(Clock())
    for _ in range(FLOOR):
        retries.try_retry('gpt-6-luna')
    model = Model('gpt-6-luna', [ProviderError('status_503'), SCENE])

    # 공급자가 아파 모두가 실패하는 동안 재시도가 일을 두 배로 키우지 않는다. 그 시도의 실패로 끝난다
    with pytest.raises(NarrationFailed, match='status_503'):
        await chain(model, retries).narrate(REQUEST)
    assert len(model.calls) == 1


async def test_without_a_budget_the_old_rule_holds():
    model = Model('gpt-6-luna', [ProviderError('status_503'), SCENE])

    assert await chain(model, None).narrate(REQUEST) == SCENE


async def test_narrators_share_the_budget_of_the_app():
    retries = budget(Clock())
    narrations = [chain(Model('gpt-6-luna', [ProviderError('status_503'), SCENE]), retries) for _ in range(FLOOR + 1)]

    results = []
    for narrator in narrations:
        try:
            results.append(await narrator.narrate(REQUEST))
        except NarrationFailed as failure:
            results.append(failure.reason)

    # 서술마다 첫 시도를 하나씩 적었다(4 번). 10% 는 0 이라 늘 되는 3 번까지만 다시 불렀다
    assert results == [SCENE] * FLOOR + ['status_503']
