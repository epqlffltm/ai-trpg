# game-server/tests/test_score_roll.py

"""
능력치의 점수를 주사위로 정하는 계산(app/engine/score_roll.py)을 검증한다.

DB 도 HTTP 도 쓰지 않는다. 정해진 눈을 내는 주사위를 꽂아 결과를 그대로 견준다.
"""

import pytest

from app.engine.dice import ScriptedDice
from app.engine.ruleset import Ruleset
from app.engine.score_roll import RolledScore, keep_highest, roll_score, roll_scores, uses_exactly
from app.engine.templates import SRD5

SCORE_ROLL = SRD5.score_roll


def rules(**changes) -> Ruleset:
    """SRD5 템플릿에서 몇 칸만 바꾼 규칙."""
    return Ruleset.model_validate({**SRD5.model_dump(mode='json'), **changes})


# 능력치가 둘뿐이고 2d10 을 모두 더하는 규칙. SRD5 와 다른 규칙에서도 같은 함수가 도는지 본다
TWO_ABILITIES = rules(
    abilities=[{'key': 'body', 'name': '몸'}, {'key': 'mind', 'name': '마음'}],
    hp_ability='body',
    score_roll={'count': 2, 'sides': 10, 'keep': 2},
)


class WatchedDice:
    """굴릴 때마다 몇 면짜리를 굴렸는지 적어 두는 주사위. 늘 1 이 나온다."""

    def __init__(self) -> None:
        self.sides: list[int] = []

    def roll(self, sides: int) -> int:
        self.sides.append(sides)
        return 1


def abilities(*scores: int) -> dict[str, int]:
    """점수 여섯을 SRD5 의 능력치에 차례로 놓는다."""
    return dict(zip(['str', 'dex', 'con', 'int', 'wis', 'cha'], scores, strict=True))


# --- 높은 것만 더하기 ---


@pytest.mark.parametrize(
    ('dice', 'keep', 'total'),
    [
        ((6, 5, 3, 1), 3, 14),
        # 굴린 순서와 상관없다
        ((1, 3, 5, 6), 3, 14),
        ((3, 6, 1, 5), 3, 14),
        # 같은 눈이 여럿이면 하나만 버린다
        ((4, 4, 4, 4), 3, 12),
        ((1, 1, 1, 1), 3, 3),
        ((6, 6, 6, 6), 3, 18),
        # 모두 더하는 규칙
        ((2, 9), 2, 11),
        # 하나만 남기는 규칙
        ((2, 9, 4), 1, 9),
    ],
)
def test_keeps_the_highest_dice(dice: tuple[int, ...], keep: int, total: int):
    assert keep_highest(dice, keep) == total


# --- 점수 하나 ---


def test_a_score_remembers_every_die_that_was_rolled():
    rolled = roll_score(SCORE_ROLL, ScriptedDice([1, 6, 3, 5]))

    # 버린 눈(1)도 남긴다. 굴린 순서 그대로다
    assert rolled == RolledScore(dice=(1, 6, 3, 5), score=14)


def test_a_score_rolls_the_dice_the_rules_say():
    dice = WatchedDice()

    roll_score(SCORE_ROLL, dice)

    assert dice.sides == [6, 6, 6, 6]


# --- 능력치의 수만큼 ---


def test_rolls_one_score_for_each_ability():
    # 4d6 여섯 번. 눈 스물넷을 쓴다
    dice = ScriptedDice([6, 6, 6, 6, 5, 5, 5, 5, 4, 4, 4, 4, 3, 3, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1])

    rolled = roll_scores(SRD5, dice)

    assert [score.score for score in rolled] == [18, 15, 12, 9, 6, 3]
    assert rolled[0].dice == (6, 6, 6, 6)
    assert dice.remaining == 0


def test_another_ruleset_rolls_its_own_way():
    dice = WatchedDice()

    rolled = roll_scores(TWO_ABILITIES, dice)

    # 능력치가 둘이라 두 번, 한 번에 10 면 둘을 굴린다
    assert dice.sides == [10, 10, 10, 10]
    assert [score.score for score in rolled] == [2, 2]


def test_nothing_is_rolled_when_the_rules_have_no_score_roll():
    dice = ScriptedDice([6])

    assert roll_scores(rules(score_roll=None), dice) is None
    # 주사위를 건드리지 않았다
    assert dice.remaining == 1


# --- 굴린 점수를 능력치에 놓기 ---

ROLLED = [15, 14, 13, 12, 10, 8]


def test_the_scores_may_be_placed_on_any_ability():
    assert uses_exactly(ROLLED, abilities(15, 14, 13, 12, 10, 8))
    assert uses_exactly(ROLLED, abilities(8, 10, 12, 13, 14, 15))
    assert uses_exactly(ROLLED, abilities(13, 8, 15, 10, 14, 12))


@pytest.mark.parametrize(
    'placed',
    [
        # 굴리지 않은 점수를 적었다
        abilities(16, 14, 13, 12, 10, 8),
        # 좋은 점수를 두 번 썼다
        abilities(15, 15, 13, 12, 10, 8),
        # 나쁜 점수를 버리고 다른 것을 한 번 더 썼다
        abilities(15, 14, 13, 12, 10, 10),
        # 다 놓지 않았다
        {'str': 15, 'dex': 14},
        {},
    ],
    ids=['not rolled', 'used twice', 'dropped the worst', 'not all placed', 'nothing placed'],
)
def test_every_rolled_score_is_used_once_and_only_once(placed: dict[str, int]):
    assert not uses_exactly(ROLLED, placed)


def test_a_score_that_came_up_twice_is_used_twice():
    twice = [12, 12, 9, 9, 9, 7]

    assert uses_exactly(twice, abilities(9, 12, 9, 7, 12, 9))
    # 두 번 나온 것을 세 번 쓸 수는 없다
    assert not uses_exactly(twice, abilities(12, 12, 12, 9, 9, 7))
