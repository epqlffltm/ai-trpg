# game-server/tests/test_action.py

"""
행동의 모양과, 행동이 규칙에 맞는지 보는 함수(app/engine/action.py)를 검증한다.

DB 도 HTTP 도 쓰지 않는다.
"""

import pytest
from pydantic import ValidationError

from app.engine.action import ActionKind, CheckAction, attempt, find_fault, settle
from app.engine.check import Check
from app.engine.dice import ScriptedDice
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5

# 능력치가 둘뿐이고 난이도가 하나뿐인 규칙. SRD5 와 다른 규칙에서도 같은 함수가 도는지 본다
SMALL_RULES = Ruleset.model_validate(
    {
        **SRD5.model_dump(mode='json'),
        'abilities': [{'key': 'body', 'name': '몸'}, {'key': 'mind', 'name': '마음'}],
        'difficulties': [{'key': 'normal', 'name': '보통', 'target': 7}],
        'default_difficulty': 'normal',
    }
)


def check(ability: str = 'str', difficulty: str | None = None) -> CheckAction:
    return CheckAction(kind=ActionKind.CHECK, ability=ability, difficulty=difficulty)


# --- 모양 ---


def test_reads_an_action():
    action = CheckAction.model_validate({'kind': 'check', 'ability': 'dex', 'difficulty': 'hard'})

    assert (action.kind, action.ability, action.difficulty) == (ActionKind.CHECK, 'dex', 'hard')


def test_the_difficulty_may_be_left_out():
    assert CheckAction.model_validate({'kind': 'check', 'ability': 'dex'}).difficulty is None


@pytest.mark.parametrize(
    'document',
    [
        # 종류를 적어야 한다. 종류가 늘어도 무엇을 하려는지 헷갈리지 않는다
        {'ability': 'dex'},
        {'kind': 'attack', 'ability': 'dex'},
        {'kind': 'check'},
        {'kind': 'check', 'ability': 'DEX'},
        {'kind': 'check', 'ability': '민첩'},
        # 난이도는 단계의 이름으로 받는다. 숫자를 직접 받지 않는다
        {'kind': 'check', 'ability': 'dex', 'difficulty': 15},
        {'kind': 'check', 'ability': 'dex', 'target': 5},
        # 결과를 적어 보낼 수 없다. 결과는 엔진이 정한다
        {'kind': 'check', 'ability': 'dex', 'roll': 20},
        {'kind': 'check', 'ability': 'dex', 'success': True},
    ],
)
def test_rejects_an_action_with_a_bad_shape(document: dict):
    with pytest.raises(ValidationError):
        CheckAction.model_validate(document)


# --- 규칙에 맞는가 ---


@pytest.mark.parametrize(
    ('action', 'fault'),
    [
        (check('str', 'hard'), None),
        (check('cha'), None),
        (check('luck', 'hard'), 'ability'),
        (check('str', 'impossible'), 'difficulty'),
        # 둘 다 틀리면 능력을 먼저 알린다
        (check('luck', 'impossible'), 'ability'),
    ],
)
def test_finds_what_does_not_fit_the_rules(action: CheckAction, fault: str | None):
    assert find_fault(SRD5, action) == fault


def test_fitting_depends_on_the_rules():
    # 같은 행동이 한 규칙에는 맞고 다른 규칙에는 안 맞는다
    assert find_fault(SMALL_RULES, check('body', 'normal')) is None
    assert find_fault(SRD5, check('body', 'normal')) == 'ability'
    assert find_fault(SMALL_RULES, check('str')) == 'ability'
    assert find_fault(SMALL_RULES, check('body', 'hard')) == 'difficulty'


# --- 난이도 채우기 ---


def test_settling_fills_in_the_default_difficulty():
    assert settle(SRD5, check('str')).difficulty == 'medium'
    assert settle(SMALL_RULES, check('body')).difficulty == 'normal'


def test_settling_keeps_a_chosen_difficulty():
    assert settle(SRD5, check('str', 'very_hard')).difficulty == 'very_hard'


def test_settling_does_not_change_the_action_it_was_given():
    action = check('str')

    settled = settle(SRD5, action)

    assert action.difficulty is None
    assert settled == check('str', 'medium')


# --- 행동을 한다 ---

# 근력 16(보정 +3), 매력 8(보정 -1)
ABILITIES = {'str': 16, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10, 'cha': 8}


def test_attempting_uses_the_score_of_the_ability_named():
    strong = attempt(SRD5, check('str', 'medium'), ABILITIES, ScriptedDice([12]))
    rude = attempt(SRD5, check('cha', 'medium'), ABILITIES, ScriptedDice([12]))

    # 같은 눈, 같은 난이도다. 어느 능력으로 하느냐가 성패를 가른다
    assert strong == Check(roll=12, modifier=3, total=15, target=15, success=True)
    assert rude == Check(roll=12, modifier=-1, total=11, target=15, success=False)


def test_attempting_aims_at_the_difficulty_named():
    easy = attempt(SRD5, check('dex', 'easy'), ABILITIES, ScriptedDice([12]))
    hard = attempt(SRD5, check('dex', 'hard'), ABILITIES, ScriptedDice([12]))

    assert (easy.target, easy.success) == (10, True)
    assert (hard.target, hard.success) == (20, False)


def test_attempting_rolls_once():
    dice = ScriptedDice([12, 20])

    attempt(SRD5, check('str', 'medium'), ABILITIES, dice)

    assert dice.remaining == 1


def test_attempting_works_under_other_rules():
    result = attempt(SMALL_RULES, check('body', 'normal'), {'body': 14, 'mind': 10}, ScriptedDice([5]))

    assert result == Check(roll=5, modifier=2, total=7, target=7, success=True)
