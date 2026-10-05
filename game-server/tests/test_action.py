# game-server/tests/test_action.py

"""
행동의 모양과, 행동이 규칙에 맞는지 보는 함수(app/engine/action.py)를 검증한다.

DB 도 HTTP 도 쓰지 않는다.
"""

import pytest
from pydantic import ValidationError

from app.engine.action import ActionKind, CheckAction, find_fault, settle
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
