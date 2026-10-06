# game-server/tests/test_engine_health.py

"""
HP 를 바꾸는 계산(app/engine/health.py)을 검증한다.

DB 도 HTTP 도 쓰지 않는다.
"""

import pytest

from app.engine.dice import ScriptedDice
from app.engine.health import Change, ChangeKind, change_hp, find_magnitude, heal, hurt, is_downed, roll_amount
from app.engine.ruleset import Magnitude
from app.engine.templates import SRD5

LIGHT = find_magnitude(SRD5, 'light')
HEAVY = find_magnitude(SRD5, 'heavy')


class WatchedDice:
    """굴릴 때마다 몇 면짜리를 굴리라고 했는지 적어 두는 주사위. 늘 1 을 낸다."""

    def __init__(self) -> None:
        self.asked: list[int] = []

    def roll(self, sides: int) -> int:
        self.asked.append(sides)
        return 1


# --- 양의 등급 ---


def test_finds_a_magnitude_of_the_rules():
    assert find_magnitude(SRD5, 'heavy') == Magnitude(key='heavy', name='심함', count=2, sides=8)
    assert find_magnitude(SRD5, 'deadly') is None


@pytest.mark.parametrize(('key', 'asked'), [('light', [4]), ('moderate', [8]), ('heavy', [8, 8])])
def test_rolls_the_dice_the_magnitude_names(key: str, asked: list[int]):
    dice = WatchedDice()

    roll_amount(find_magnitude(SRD5, key), dice)

    # 개수와 면 수가 규칙에서 온다
    assert dice.asked == asked


def test_gives_the_rolls_in_order():
    assert roll_amount(HEAVY, ScriptedDice([3, 7])) == (3, 7)


# --- 피해와 회복 ---


@pytest.mark.parametrize(('hp', 'amount', 'left'), [(10, 3, 7), (10, 10, 0), (3, 8, 0), (0, 5, 0), (10, 0, 10)])
def test_damage_stops_at_zero(hp: int, amount: int, left: int):
    assert hurt(hp, amount) == left


@pytest.mark.parametrize(('hp', 'amount', 'after'), [(3, 4, 7), (7, 3, 10), (7, 8, 10), (0, 2, 2), (10, 5, 10)])
def test_recovery_stops_at_the_maximum(hp: int, amount: int, after: int):
    assert heal(hp, 10, amount) == after


@pytest.mark.parametrize(('hp', 'downed'), [(0, True), (1, False), (10, False)])
def test_zero_hp_means_downed(hp: int, downed: bool):
    assert is_downed(hp) is downed


# --- HP 를 한 번 바꾼다 ---


def test_damage_takes_the_sum_of_the_dice():
    change = change_hp(ChangeKind.DAMAGE, HEAVY, hp=10, max_hp=10, dice=ScriptedDice([3, 4]))

    assert change == Change(kind=ChangeKind.DAMAGE, rolls=(3, 4), amount=7, before=10, after=3)
    assert change.downed is False


def test_damage_past_zero_downs_the_character():
    change = change_hp(ChangeKind.DAMAGE, HEAVY, hp=5, max_hp=10, dice=ScriptedDice([8, 8]))

    # 주사위가 정한 양은 16 이지만 HP 는 0 에서 멈춘다. 양과 실제로 바뀐 것을 둘 다 남긴다
    assert (change.amount, change.before, change.after) == (16, 5, 0)
    assert change.downed is True


def test_recovery_adds_the_sum_of_the_dice():
    change = change_hp(ChangeKind.RECOVERY, LIGHT, hp=0, max_hp=10, dice=ScriptedDice([3]))

    assert change == Change(kind=ChangeKind.RECOVERY, rolls=(3,), amount=3, before=0, after=3)
    # 쓰러져 있던 캐릭터가 일어났다
    assert change.downed is False


def test_recovery_past_the_maximum_is_cut():
    change = change_hp(ChangeKind.RECOVERY, LIGHT, hp=9, max_hp=10, dice=ScriptedDice([4]))

    assert (change.amount, change.before, change.after) == (4, 9, 10)


def test_changing_hp_rolls_only_the_dice_of_the_magnitude():
    dice = ScriptedDice([3, 4, 8])

    change_hp(ChangeKind.DAMAGE, HEAVY, hp=10, max_hp=10, dice=dice)

    assert dice.remaining == 1


def test_a_change_cannot_be_rewritten():
    change = change_hp(ChangeKind.DAMAGE, LIGHT, hp=10, max_hp=10, dice=ScriptedDice([2]))

    with pytest.raises(AttributeError):
        change.after = 10
