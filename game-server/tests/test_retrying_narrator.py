# game-server/tests/test_retrying_narrator.py

"""
다시 시도하고 다음 모델로 넘어가는 서술자(app/rounds/retrying_narrator.py)를 검증한다.

모델을 부르지 않는다. 정해 둔 대로 답하거나 실패하는 서술자를 모델 자리에 꽂는다.
시계와 쉬는 것도 가짜다. 테스트가 실제로 쉬지 않고, 시간이 얼마나 흘렀는지를 테스트가 정한다.

보는 것은 넷이다.
  - 다시 시도할 실패와 안 할 실패를 나눈다. 다음 모델로 넘어갈 실패와 안 넘어갈 실패도 나눈다.
  - 모델마다 두 번까지 부르고, 다시 부르기 전에 쉰다.
  - 서술 하나의 시간 상한을 넘겨 가며 새로 부르지 않는다.
  - 시도 하나하나가 따로 기록된다.
"""

from dataclasses import dataclass, field

import pytest

from app.ai.calls import Outcome
from app.ai.fake import FakeCallLog
from app.ai.provider import ChatMessage, Completion, GenerationParams, ProviderError
from app.rounds.llm_narrator import LLMNarrator, NarrationError
from app.rounds.narrator import Move, NarrationRequest, StoryContext
from app.rounds.retrying_narrator import (
    PAUSE_SECONDS,
    NarrationFailed,
    RetryingNarrator,
    can_fall_back,
    can_retry,
    random_pause,
)

REQUEST = NarrationRequest(
    round_number=1,
    scene='사이렌이 울린다.',
    moves=[Move('엘프', '달린다.')],
    story=StoryContext(title='추격전', rating='all', guide=''),
)
SCENE = '엔진 소리가 골목을 메운다.'
# 한 번 부르는 시간의 상한과 서술 하나의 상한. 실제 설정과 같은 값이다
TIMEOUT = 60.0
BUDGET = 150.0


class Clock:
    """테스트가 돌리는 시계. 부르는 데, 쉬는 데 시간이 흐른 것처럼 한다."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@dataclass
class Script:
    """
    정해 둔 대로 하는 서술자. outcomes 를 차례로 꺼내, 글이면 돌려주고 예외면 올린다.

    부를 때마다 이름을 calls 에 적고, 시계를 cost 초만큼 돌린다(모델이 답하는 데 걸린 시간).
    """

    name: str
    outcomes: list
    clock: Clock
    calls: list[str]
    cost: float = 0.0

    async def narrate(self, request: NarrationRequest) -> str:
        self.calls.append(self.name)
        self.clock.now += self.cost
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@dataclass
class Setup:
    """한 테스트의 시계, 부른 순서, 쉰 시간."""

    clock: Clock = field(default_factory=Clock)
    calls: list[str] = field(default_factory=list)
    pauses: list[float] = field(default_factory=list)

    def model(self, name: str, *outcomes, cost: float = 0.0) -> Script:
        return Script(name, list(outcomes), self.clock, self.calls, cost)

    async def sleep(self, seconds: float) -> None:
        self.pauses.append(seconds)
        self.clock.now += seconds

    def narrator(self, *models: Script) -> RetryingNarrator:
        return RetryingNarrator(
            list(models),
            attempt_timeout=TIMEOUT,
            budget=BUDGET,
            pause=lambda: 1.5,
            sleep=self.sleep,
            clock=self.clock,
        )


# --- 무엇을 다시, 무엇을 넘기나 ---


@pytest.mark.parametrize(
    'reason',
    [
        'timeout',
        'unreachable',
        'interrupted',
        'stream_error',
        'malformed',
        'status_429',
        'status_500',
        'status_503',
        'cut_off',
        'empty',
    ],
)
def test_a_passing_failure_is_worth_another_try(reason: str):
    # 일시적인 실패이거나, 모델의 글이 매번 달라서 다시 부르면 나을 수 있다
    assert can_retry(reason)


@pytest.mark.parametrize('reason', ['status_400', 'status_401', 'status_403', 'status_404', 'status_422', 'no_story'])
def test_a_wrong_request_is_not_sent_again_to_the_same_model(reason: str):
    # 요청이나 설정이 틀렸다. 같은 것을 보내면 또 실패한다
    assert not can_retry(reason)


@pytest.mark.parametrize('reason', ['unreachable', 'status_401', 'status_403', 'no_story'])
def test_some_failures_are_not_fixed_by_another_model(reason: str):
    # 모델들은 같은 서버에 있다. 서버가 꺼졌거나 권한이 없으면 어느 모델도 안 된다
    assert not can_fall_back(reason)


@pytest.mark.parametrize('reason', ['status_404', 'status_400', 'timeout', 'cut_off'])
def test_other_failures_may_be_fixed_by_another_model(reason: str):
    # 그 이름의 모델이 없거나, 그 모델만 느리거나, 그 모델의 글이 이상하다
    assert can_fall_back(reason)


def test_the_pause_is_somewhere_in_its_range():
    low, high = PAUSE_SECONDS

    assert all(low <= random_pause() <= high for _ in range(50))


# --- 부르는 순서 ---


async def test_a_good_first_answer_is_used_at_once():
    setup = Setup()

    scene = await setup.narrator(setup.model('first', SCENE)).narrate(REQUEST)

    assert scene == SCENE
    assert (setup.calls, setup.pauses) == (['first'], [])


async def test_a_passing_failure_is_tried_again_after_a_pause():
    setup = Setup()

    scene = await setup.narrator(setup.model('first', ProviderError('timeout'), SCENE)).narrate(REQUEST)

    assert scene == SCENE
    assert (setup.calls, setup.pauses) == (['first', 'first'], [1.5])


async def test_after_two_tries_the_next_model_is_called():
    setup = Setup()
    first = setup.model('first', NarrationError('cut_off'), NarrationError('cut_off'))
    second = setup.model('second', SCENE)

    scene = await setup.narrator(first, second).narrate(REQUEST)

    # 모델마다 두 번까지다. 다음 모델은 쉬지 않고 바로 부른다
    assert scene == SCENE
    assert (setup.calls, setup.pauses) == (['first', 'first', 'second'], [1.5])


async def test_a_wrong_request_moves_on_without_trying_again():
    setup = Setup()
    first = setup.model('first', ProviderError('status_404'))
    second = setup.model('second', SCENE)

    scene = await setup.narrator(first, second).narrate(REQUEST)

    assert scene == SCENE
    assert setup.calls == ['first', 'second']


async def test_a_server_that_is_down_is_tried_again_but_not_with_another_model():
    setup = Setup()
    first = setup.model('first', ProviderError('unreachable'), ProviderError('unreachable'))
    second = setup.model('second', SCENE)

    with pytest.raises(NarrationFailed) as caught:
        await setup.narrator(first, second).narrate(REQUEST)

    # 같은 서버의 다른 모델도 닿지 않는다. 부르지 않는다
    assert caught.value.reason == 'unreachable'
    assert setup.calls == ['first', 'first']


async def test_no_permission_stops_at_once():
    setup = Setup()
    first = setup.model('first', ProviderError('status_401'))
    second = setup.model('second', SCENE)

    with pytest.raises(NarrationFailed) as caught:
        await setup.narrator(first, second).narrate(REQUEST)

    assert caught.value.reason == 'status_401'
    assert setup.calls == ['first']


async def test_when_every_model_fails_the_last_reason_is_given():
    setup = Setup()
    first = setup.model('first', ProviderError('timeout'), ProviderError('timeout'))
    second = setup.model('second', NarrationError('empty'), NarrationError('too_long'))

    with pytest.raises(NarrationFailed) as caught:
        await setup.narrator(first, second).narrate(REQUEST)

    assert caught.value.reason == 'too_long'
    assert setup.calls == ['first', 'first', 'second', 'second']


async def test_a_bug_is_not_tried_again():
    setup = Setup()
    first = setup.model('first', RuntimeError('버그'), SCENE)

    # 서술자의 실패가 아닌 예외는 버그다. 다시 불러 감추지 않는다
    with pytest.raises(RuntimeError):
        await setup.narrator(first).narrate(REQUEST)
    assert setup.calls == ['first']


# --- 시간의 상한 ---


async def test_no_new_call_starts_when_it_could_run_past_the_budget():
    setup = Setup()
    # 부를 때마다 timeout 끝까지 기다렸다가 실패한다
    first = setup.model('first', ProviderError('timeout'), ProviderError('timeout'), cost=TIMEOUT)
    second = setup.model('second', SCENE)

    with pytest.raises(NarrationFailed) as caught:
        await setup.narrator(first, second).narrate(REQUEST)

    # 0초에 첫 시도(끝 60초), 1.5초 쉬고 두 번째(끝 121.5초). 다음 모델은 121.5 + 60 > 150 이라 부르지 않는다
    assert caught.value.reason == 'timeout'
    assert setup.calls == ['first', 'first']
    assert setup.clock.now <= BUDGET


async def test_a_call_that_fits_in_what_is_left_is_made():
    setup = Setup()
    first = setup.model('first', ProviderError('timeout'), ProviderError('timeout'), cost=40.0)
    second = setup.model('second', SCENE)

    scene = await setup.narrator(first, second).narrate(REQUEST)

    # 40 + 1.5 + 40 = 81.5 초. 81.5 + 60 <= 150 이라 다음 모델을 부른다
    assert scene == SCENE
    assert setup.calls == ['first', 'first', 'second']


# --- 기록 ---


@dataclass
class FlakyProvider:
    """처음 한 번은 실패하고, 그다음부터는 답하는 provider."""

    kind = 'flaky'
    model = 'flaky-model'
    failed: bool = False

    async def complete(self, messages: list[ChatMessage], params: GenerationParams) -> Completion:
        if not self.failed:
            self.failed = True
            raise ProviderError('timeout')
        return Completion(text=SCENE, model=self.model)


async def test_every_try_is_recorded_on_its_own():
    log = FakeCallLog()
    setup = Setup()
    narrator = RetryingNarrator(
        [LLMNarrator(FlakyProvider(), log)], attempt_timeout=TIMEOUT, budget=BUDGET, sleep=setup.sleep
    )

    scene = await narrator.narrate(REQUEST)

    # 실패한 시도도 시간을 썼다. 한 줄씩 남는다
    assert scene == SCENE
    assert [(record.outcome, record.error) for record in log.records] == [
        (Outcome.FAILED, 'timeout'),
        (Outcome.OK, None),
    ]
