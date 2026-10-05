# game-server/tests/test_check.py

"""
주사위(app/engine/dice.py)와 판정(app/engine/check.py)을 검증한다.

DB 도 HTTP 도 쓰지 않는다. 정해진 눈을 내는 주사위를 꽂아서, 같은 눈이면 같은 결과가 나오는지 본다.
"""

import pytest

from app.engine.check import Check, find_ability, find_difficulty, modifier_of, resolve
from app.engine.dice import RandomDice, ScriptedDice
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5

# 점수가 곧 보정이고 6면 주사위를 쓰는 규칙. SRD5 와 다른 규칙에서도 같은 함수가 도는지 본다
PLAIN_RULES = Ruleset.model_validate(
    {
        **SRD5.model_dump(mode='json'),
        'modifier': {'base': 0, 'step': 1},
        'die': 6,
        'difficulties': [{'key': 'normal', 'name': '보통', 'target': 7}],
        'default_difficulty': 'normal',
    }
)

MEDIUM = find_difficulty(SRD5, 'medium')


# --- 주사위 ---


def test_the_scripted_dice_gives_its_rolls_in_order():
    dice = ScriptedDice([3, 20, 1])

    assert [dice.roll(20), dice.roll(20), dice.roll(20)] == [3, 20, 1]
    assert dice.remaining == 0


def test_the_scripted_dice_fails_loudly_when_it_runs_out():
    dice = ScriptedDice([3])
    dice.roll(20)

    # 테스트가 생각한 것보다 한 번 더 굴렸다. 조용히 넘어가지 않는다
    with pytest.raises(IndexError):
        dice.roll(20)


@pytest.mark.parametrize('value', [0, 7, -1])
def test_the_scripted_dice_rejects_a_roll_the_die_cannot_show(value: int):
    with pytest.raises(ValueError, match='6 면'):
        ScriptedDice([value]).roll(6)


@pytest.mark.parametrize('sides', [2, 6, 20])
def test_the_real_dice_shows_every_face_and_nothing_else(sides: int):
    dice = RandomDice()

    rolls = {dice.roll(sides) for _ in range(2000)}

    # 2,000 번을 굴리면 모든 면이 한 번은 나온다. 20면에서 한 면이 빠질 확률은 10의 -43 제곱쯤이다
    assert rolls == set(range(1, sides + 1))


# --- 규칙에서 찾기 ---


def test_finds_an_ability_of_the_rules():
    assert find_ability(SRD5, 'dex').name == '민첩'
    assert find_ability(SRD5, 'luck') is None


def test_finds_a_difficulty_of_the_rules():
    assert find_difficulty(SRD5, 'hard').target == 20
    assert find_difficulty(SRD5, 'impossible') is None


def test_no_key_means_the_default_difficulty():
    assert find_difficulty(SRD5, None).key == 'medium'
    assert find_difficulty(PLAIN_RULES, None).key == 'normal'


# --- 보정 ---


@pytest.mark.parametrize(
    ('score', 'expected'),
    [(1, -5), (7, -2), (8, -1), (9, -1), (10, 0), (11, 0), (12, 1), (13, 1), (14, 2), (19, 4), (20, 5)],
)
def test_the_modifier_rounds_down(score: int, expected: int):
    # 9 는 -0.5 가 아니라 -1 이다. 0 쪽으로 버리지 않고 아래로 내린다
    assert modifier_of(SRD5, score) == expected


@pytest.mark.parametrize('score', [0, 3, 5])
def test_the_modifier_follows_the_rules(score: int):
    # 이 규칙에서는 점수가 곧 보정이다. 계산식은 같고 값만 다르다
    assert modifier_of(PLAIN_RULES, score) == score


# --- 판정 ---


def test_a_check_adds_the_modifier_to_the_roll():
    check = resolve(SRD5, score=14, difficulty=MEDIUM, dice=ScriptedDice([11]))

    assert check == Check(roll=11, modifier=2, total=13, target=15, success=False)


@pytest.mark.parametrize(
    ('roll', 'success'),
    [(12, False), (13, True), (14, True)],
)
def test_meeting_the_target_exactly_is_a_success(roll: int, success: bool):
    # 점수 14 는 보정 +2 다. 목표값 15 에는 눈 13 이 꼭 맞는다
    check = resolve(SRD5, score=14, difficulty=MEDIUM, dice=ScriptedDice([roll]))

    assert check.total == roll + 2
    assert check.success is success


def test_a_low_score_takes_away_from_the_roll():
    check = resolve(SRD5, score=6, difficulty=find_difficulty(SRD5, 'very_easy'), dice=ScriptedDice([6]))

    # 점수 6 은 보정 -2 다. 눈 6 이 4 가 되어 목표값 5 에 못 미친다
    assert (check.modifier, check.total, check.success) == (-2, 4, False)


def test_the_highest_and_lowest_rolls_follow_the_same_arithmetic():
    easy = find_difficulty(SRD5, 'very_easy')
    hardest = find_difficulty(SRD5, 'very_hard')

    lowest = resolve(SRD5, score=20, difficulty=easy, dice=ScriptedDice([1]))
    highest = resolve(SRD5, score=1, difficulty=hardest, dice=ScriptedDice([20]))

    # 눈 1 이 저절로 실패하거나 눈 20 이 저절로 성공하지 않는다. 더한 값만 본다
    assert (lowest.total, lowest.success) == (6, True)
    assert (highest.total, highest.success) == (15, False)


class WatchedDice:
    """굴릴 때마다 몇 면짜리를 굴리라고 했는지 적어 두는 주사위. 늘 1 을 낸다."""

    def __init__(self) -> None:
        self.asked: list[int] = []

    def roll(self, sides: int) -> int:
        self.asked.append(sides)
        return 1


@pytest.mark.parametrize(('ruleset', 'sides'), [(SRD5, 20), (PLAIN_RULES, 6)], ids=['d20', 'd6'])
def test_a_check_rolls_the_die_of_the_rules_once(ruleset: Ruleset, sides: int):
    dice = WatchedDice()

    resolve(ruleset, score=10, difficulty=find_difficulty(ruleset, None), dice=dice)

    # 주사위의 면 수는 규칙에서 온다. 한 번만 굴린다
    assert dice.asked == [sides]


def test_a_check_works_under_other_rules():
    check = resolve(PLAIN_RULES, score=1, difficulty=find_difficulty(PLAIN_RULES, None), dice=ScriptedDice([6]))

    # 6면 주사위, 점수가 곧 보정, 목표값 7. 계산하는 코드는 같다
    assert check == Check(roll=6, modifier=1, total=7, target=7, success=True)


def test_the_same_roll_gives_the_same_result():
    first = resolve(SRD5, score=12, difficulty=MEDIUM, dice=ScriptedDice([15]))
    second = resolve(SRD5, score=12, difficulty=MEDIUM, dice=ScriptedDice([15]))

    assert first == second
