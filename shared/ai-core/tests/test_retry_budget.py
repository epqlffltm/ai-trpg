# shared/ai-core/tests/test_retry_budget.py

"""
재시도 예산(ai_core/retry_budget.py)을 검증한다.

보는 것.
  - 비율: 최근 창 안의 첫 시도 수의 10% 까지만 다시 부른다. 손님이 적어도 3 번은 늘 된다.
  - 창: 창 밖으로 나간 시도는 세지 않는다.
  - 모델마다 따로 센다.

예산을 쓰는 다시 시도하는 서술자는 게임 서버의 테스트(trpg-server/tests/test_retry_budget.py)가 본다.
"""

from dataclasses import dataclass

import pytest

from ai_core.retry_budget import FLOOR, RATIO, WINDOW_SECONDS, RetryBudget, allowance


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
