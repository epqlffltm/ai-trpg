# game-server/tests/test_death.py

"""
죽음의 굴림의 계산(app/engine/death.py)을 검증한다.

DB 도 HTTP 도 쓰지 않는다. 정해진 눈을 내는 주사위를 꽂아 결과를 그대로 견준다.
"""

import pytest

from app.engine.death import DeathSaveRoll, Fate, fate_of, is_rolling, roll_death_save
from app.engine.dice import ScriptedDice
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5

DEATH_SAVE = SRD5.death_save


def rules(**changes) -> Ruleset:
    """SRD5 템플릿에서 몇 칸만 바꾼 규칙."""
    return Ruleset.model_validate({**SRD5.model_dump(mode='json'), **changes})


# d6 을 굴려 5 이상이어야 성공하고, 실패 한 번에 죽고, 성공 둘이면 고비를 넘기는 규칙.
# SRD5 와 다른 규칙에서도 같은 함수가 도는지 본다. 점수의 범위에 맞지 않는 칸은 뺀다
HARSH = rules(die=6, death_save={'target': 5, 'successes': 2, 'failures': 1})


class WatchedDice:
    """굴릴 때마다 몇 면짜리를 굴렸는지 적어 두는 주사위. 늘 1 이 나온다."""

    def __init__(self) -> None:
        self.sides: list[int] = []

    def roll(self, sides: int) -> int:
        self.sides.append(sides)
        return 1


# --- 센 것으로 갈림길을 정한다 ---


@pytest.mark.parametrize(
    ('successes', 'failures', 'fate'),
    [
        (0, 0, Fate.DYING),
        (2, 2, Fate.DYING),
        (3, 0, Fate.STABLE),
        (3, 2, Fate.STABLE),
        (0, 3, Fate.DEAD),
        (2, 3, Fate.DEAD),
        # 둘이 함께 찰 수는 없지만, 찼다면 죽은 것으로 본다
        (3, 3, Fate.DEAD),
    ],
)
def test_the_fate_comes_from_the_counts(successes: int, failures: int, fate: Fate):
    assert fate_of(DEATH_SAVE, successes, failures) == fate


def test_only_the_dying_keep_rolling():
    assert is_rolling(DEATH_SAVE, 2, 2)
    assert not is_rolling(DEATH_SAVE, 3, 0)
    assert not is_rolling(DEATH_SAVE, 0, 3)


# --- 한 번 굴린다 ---


@pytest.mark.parametrize(('roll', 'success'), [(10, True), (20, True), (11, True), (9, False), (1, False)])
def test_a_roll_at_or_over_the_target_is_a_success(roll: int, success: bool):
    rolled = roll_death_save(SRD5, 0, 0, ScriptedDice([roll]))

    assert (rolled.roll, rolled.target, rolled.success) == (roll, 10, success)


def test_a_success_and_a_failure_are_counted_apart():
    saved = roll_death_save(SRD5, 1, 1, ScriptedDice([15]))
    failed = roll_death_save(SRD5, 1, 1, ScriptedDice([5]))

    assert (saved.successes, saved.failures, saved.fate) == (2, 1, Fate.DYING)
    assert (failed.successes, failed.failures, failed.fate) == (1, 2, Fate.DYING)


def test_the_third_failure_kills():
    rolled = roll_death_save(SRD5, 2, 2, ScriptedDice([9]))

    assert rolled == DeathSaveRoll(roll=9, target=10, success=False, successes=2, failures=3, fate=Fate.DEAD)


def test_the_third_success_stabilizes():
    rolled = roll_death_save(SRD5, 2, 2, ScriptedDice([10]))

    assert rolled == DeathSaveRoll(roll=10, target=10, success=True, successes=3, failures=2, fate=Fate.STABLE)


def test_no_special_outcome_for_the_lowest_or_the_highest_roll():
    lowest = roll_death_save(SRD5, 0, 0, ScriptedDice([1]))
    highest = roll_death_save(SRD5, 0, 0, ScriptedDice([20]))

    # 눈 1 이 실패 둘이 되거나 눈 20 이 일으켜 세우는 일은 없다. 판정과 같이, 눈이 그대로 결과다
    assert (lowest.successes, lowest.failures) == (0, 1)
    assert (highest.successes, highest.failures) == (1, 0)


def test_the_die_of_the_rules_is_rolled_once_without_a_modifier():
    dice = WatchedDice()

    roll_death_save(SRD5, 0, 0, dice)
    roll_death_save(HARSH, 0, 0, dice)

    assert dice.sides == [20, 6]


# --- 굴리지 않는 때 ---


@pytest.mark.parametrize(('successes', 'failures'), [(3, 0), (3, 2), (0, 3), (2, 3)])
def test_a_settled_fate_is_not_rolled_again(successes: int, failures: int):
    dice = ScriptedDice([20])

    # 고비를 넘겼거나 죽었다. 더 굴리지 않는다. 죽은 캐릭터가 좋은 눈으로 살아나지 않는다
    assert roll_death_save(SRD5, successes, failures, dice) is None
    assert dice.remaining == 1


def test_nothing_is_rolled_when_the_rules_have_no_death_save():
    dice = ScriptedDice([1])

    assert roll_death_save(rules(death_save=None), 0, 0, dice) is None
    assert dice.remaining == 1


# --- 다른 규칙 ---


def test_another_ruleset_uses_its_own_numbers():
    dead = roll_death_save(HARSH, 0, 0, ScriptedDice([4]))
    saved = roll_death_save(HARSH, 1, 0, ScriptedDice([5]))

    # 실패 한 번에 죽는다. 성공 둘이면 고비를 넘긴다
    assert (dead.target, dead.fate) == (5, Fate.DEAD)
    assert saved.fate == Fate.STABLE
