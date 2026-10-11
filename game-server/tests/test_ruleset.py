# game-server/tests/test_ruleset.py

"""
규칙의 모양(app/engine/ruleset.py)과 내장 템플릿(app/engine/templates.py)을 검증한다.

DB 도 HTTP 도 쓰지 않는다. 엔진의 코드는 값을 받아 값을 돌려주므로 그대로 불러 본다.
"""

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.engine.ruleset import (
    RULESET_MAX_ABILITIES,
    RULESET_MAX_DIFFICULTIES,
    RULESET_MAX_MAGNITUDES,
    RULESET_MAX_POINT_COSTS,
    Ruleset,
    find_duplicates,
)
from app.engine.templates import DEFAULT_TEMPLATE, SRD5, TEMPLATES, Template, from_template
from tests.rules import NO_INJURIES

MIGRATIONS = Path(__file__).parent.parent / 'migrations' / 'versions'


def rules(**changes) -> dict:
    """SRD5 템플릿의 문서에서 몇 칸만 바꾼 것. 틀린 규칙을 만들어 볼 때 쓴다."""
    document = SRD5.model_dump(mode='json')
    document.update(changes)
    return document


def load_migration(name: str):
    """
    마이그레이션 파일 하나를 모듈로 읽는다. 옛 룰북에 채워 넣은 값을 꺼내 볼 때 쓴다.

    파일 이름 앞의 번호는 만들 때마다 다르다. 뒤의 이름으로 찾는다.
    """
    (path,) = MIGRATIONS.glob(f'*_{name}.py')
    spec = importlib.util.spec_from_file_location(f'{name}_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_backfill_rules() -> dict:
    """
    마이그레이션들이 옛 룰북에 채워 넣은 규칙. 차례로 거친 결과다.

    규칙 칸을 더할 때 채운 값(rulebook_rules)에, 뒤의 마이그레이션들이 채운 칸을 합친다.
    """
    rules = load_migration('rulebook_rules').RULES
    magnitudes = load_migration('rulebook_magnitudes').MAGNITUDES
    hp_ability = load_migration('rulebook_hp_ability').HP_ABILITY
    point_buy = load_migration('rulebook_point_buy').POINT_BUY
    score_roll = load_migration('rulebook_score_roll').SCORE_ROLL
    death_save = load_migration('rulebook_death_save').DEATH_SAVE
    injuries = load_migration('injuries').INJURY_RULES
    return {
        **rules,
        'magnitudes': magnitudes,
        'hp_ability': hp_ability,
        'point_buy': point_buy,
        'score_roll': score_roll,
        'death_save': death_save,
        **injuries,
    }


# --- 내장 템플릿 ---


def test_the_built_in_template_is_a_d20_rule_with_six_abilities():
    assert [ability.key for ability in SRD5.abilities] == ['str', 'dex', 'con', 'int', 'wis', 'cha']
    assert SRD5.die == 20
    assert (SRD5.score_min, SRD5.score_max) == (1, 20)
    assert {difficulty.key: difficulty.target for difficulty in SRD5.difficulties} == {
        'very_easy': 5,
        'easy': 10,
        'medium': 15,
        'hard': 20,
        'very_hard': 25,
    }
    assert SRD5.default_difficulty == 'medium'


def test_the_built_in_template_has_three_magnitudes():
    dice = {magnitude.key: (magnitude.count, magnitude.sides) for magnitude in SRD5.magnitudes}

    # 가벼움 1d4, 보통 1d8, 심함 2d8
    assert dice == {'light': (1, 4), 'moderate': (1, 8), 'heavy': (2, 8)}


def test_the_built_in_template_adds_constitution_to_hp():
    assert SRD5.hp_ability == 'con'


def test_every_template_can_be_picked():
    assert set(TEMPLATES) == set(Template)
    assert from_template(DEFAULT_TEMPLATE) == SRD5
    for template in Template:
        assert from_template(template).template == template


def test_a_ruleset_survives_the_trip_through_a_document():
    # DB 에는 문서로 들어간다. 넣었다 꺼내도 같은 규칙이어야 한다
    document = SRD5.model_dump(mode='json')

    assert Ruleset.model_validate(document) == SRD5


def test_the_migration_filled_old_rulebooks_with_the_same_rules():
    # 옛 판을 읽을 때 SRD5 를 "그때의 규칙"으로 쓴다(snapshot.upgrade_from_3, upgrade_from_5).
    # 그러니 SRD5 의 값은 마이그레이션들이 채운 값과 늘 같아야 한다. 템플릿을 고치면 이 테스트가 깨진다
    assert load_backfill_rules() == SRD5.model_dump(mode='json')


def test_a_ruleset_cannot_be_changed_after_it_is_made():
    with pytest.raises(ValidationError):
        SRD5.die = 6
    # 목록도 못 고친다. tuple 이라 더하는 메서드가 없다
    assert isinstance(SRD5.abilities, tuple)
    assert isinstance(SRD5.difficulties, tuple)
    assert isinstance(SRD5.magnitudes, tuple)


# --- 말이 안 되는 규칙 ---


@pytest.mark.parametrize(
    'changes',
    [
        {'abilities': []},
        {'abilities': [{'key': f'a{number}', 'name': '능력'} for number in range(RULESET_MAX_ABILITIES + 1)]},
        {'abilities': [{'key': 'str', 'name': '근력'}, {'key': 'str', 'name': '힘'}]},
        # 이름표는 영어 소문자로 시작한다
        {'abilities': [{'key': 'Str', 'name': '근력'}]},
        {'abilities': [{'key': '1st', 'name': '근력'}]},
        {'abilities': [{'key': 'str', 'name': '   '}]},
        # 모르는 칸은 받지 않는다
        {'abilities': [{'key': 'str', 'name': '근력', 'bonus': 3}]},
        {'difficulties': []},
        {'difficulties': [{'key': f'd{number}', 'name': '난이도', 'target': 10} for number in range(11)]},
        {'difficulties': [{'key': 'medium', 'name': '보통', 'target': 15}] * 2},
        {'difficulties': [{'key': 'medium', 'name': '보통', 'target': 0}]},
        # 기본 난이도는 단계 중 하나여야 한다
        {'default_difficulty': 'impossible'},
        {'score_min': 20, 'score_max': 1},
        {'score_min': -1},
        {'die': 1},
        {'die': 101},
        {'modifier': {'base': 10, 'step': 0}},
        {'magnitudes': []},
        {
            'magnitudes': [
                {'key': f'm{number}', 'name': '등급', 'count': 1, 'sides': 4}
                for number in range(RULESET_MAX_MAGNITUDES + 1)
            ]
        },
        {'magnitudes': [{'key': 'light', 'name': '가벼움', 'count': 1, 'sides': 4}] * 2},
        # 주사위는 하나 이상 굴리고, 면이 둘 이상이다
        {'magnitudes': [{'key': 'light', 'name': '가벼움', 'count': 0, 'sides': 4}]},
        {'magnitudes': [{'key': 'light', 'name': '가벼움', 'count': 11, 'sides': 4}]},
        {'magnitudes': [{'key': 'light', 'name': '가벼움', 'count': 1, 'sides': 1}]},
        # 양을 숫자로 직접 적지 못한다
        {'magnitudes': [{'key': 'light', 'name': '가벼움', 'amount': 3}]},
        # 최대 HP 에 닿는 능력치는 능력치 중 하나여야 한다
        {'hp_ability': 'luck'},
        {'hp_ability': 'CON'},
        # 점수제: 총점은 1 이상이고, 값표는 비어 있지 않고, 같은 점수가 두 번 없고, 값은 음수가 아니다
        {'point_buy': {'budget': 0, 'costs': [{'score': 10, 'cost': 0}]}},
        {'point_buy': {'budget': 27, 'costs': []}},
        {'point_buy': {'budget': 27, 'costs': [{'score': 10, 'cost': 0}, {'score': 10, 'cost': 1}]}},
        {'point_buy': {'budget': 27, 'costs': [{'score': 10, 'cost': -1}]}},
        {
            'score_max': 100,
            'point_buy': {
                'budget': 27,
                'costs': [{'score': number + 1, 'cost': 0} for number in range(RULESET_MAX_POINT_COSTS + 1)],
            },
        },
        # 살 수 있는 점수는 규칙의 점수 범위(1~20) 안이어야 한다
        {'point_buy': {'budget': 27, 'costs': [{'score': 21, 'cost': 0}]}},
        {'point_buy': {'budget': 27, 'costs': [{'score': 0, 'cost': 0}]}},
        # 값을 식으로 적지 못한다. 값은 표에 있는 숫자뿐이다
        {'point_buy': {'budget': 27, 'costs': [{'score': 10, 'cost': 0}], 'formula': 'score - 8'}},
        # 주사위로 정하는 법: 하나 이상 굴리고, 면이 둘 이상이고, 굴린 것보다 많이 더할 수 없다
        {'score_roll': {'count': 0, 'sides': 6, 'keep': 1}},
        {'score_roll': {'count': 11, 'sides': 6, 'keep': 3}},
        {'score_roll': {'count': 4, 'sides': 1, 'keep': 3}},
        {'score_roll': {'count': 4, 'sides': 6, 'keep': 0}},
        {'score_roll': {'count': 4, 'sides': 6, 'keep': 5}},
        # 나올 점수(2~12)는 범위 안이지만, 하나를 굴려 둘을 더할 수는 없다
        {'score_roll': {'count': 1, 'sides': 6, 'keep': 2}},
        # 나올 수 있는 점수가 규칙의 점수 범위(1~20)를 벗어난다. 4d6 을 모두 더하면 24 까지 나온다
        {'score_roll': {'count': 4, 'sides': 6, 'keep': 4}},
        {'score_roll': {'count': 3, 'sides': 8, 'keep': 3}},
        # 가장 작은 점수(3)가 범위의 아래(5)보다 작다
        {'score_min': 5, 'score_roll': {'count': 4, 'sides': 6, 'keep': 3}},
        # 몇 번 굴리는지는 적지 않는다. 능력치의 수만큼이다
        {'score_roll': {'count': 4, 'sides': 6, 'keep': 3, 'times': 7}},
        # 죽음의 굴림: 목표값과 모을 수는 1 이상이고, 모을 수는 10 을 넘지 않는다
        {'death_save': {'target': 0, 'successes': 3, 'failures': 3}},
        {'death_save': {'target': 10, 'successes': 0, 'failures': 3}},
        {'death_save': {'target': 10, 'successes': 3, 'failures': 0}},
        {'death_save': {'target': 10, 'successes': 11, 'failures': 3}},
        {'death_save': {'target': 10, 'successes': 3, 'failures': 11}},
        # 목표값이 주사위의 가장 큰 눈(20)보다 크면 성공할 수 없다
        {'death_save': {'target': 21, 'successes': 3, 'failures': 3}},
        {'die': 6, 'death_save': {'target': 10, 'successes': 3, 'failures': 3}},
        # 능력치의 보정이나 다른 주사위를 적지 못한다. 규칙의 주사위를 그대로 굴린다
        {'death_save': {'target': 10, 'successes': 3, 'failures': 3, 'ability': 'con'}},
        {'death_save': {'target': 10, 'successes': 3, 'failures': 3, 'die': 6}},
        {'unknown': 1},
    ],
)
def test_rejects_a_ruleset_that_makes_no_sense(changes: dict):
    with pytest.raises(ValidationError):
        Ruleset.model_validate(rules(**changes))


def test_the_limits_themselves_are_allowed():
    most_abilities = [{'key': f'a{number}', 'name': '능력'} for number in range(RULESET_MAX_ABILITIES)]
    most_difficulties = [
        {'key': f'd{number}', 'name': '난이도', 'target': 10} for number in range(RULESET_MAX_DIFFICULTIES)
    ]

    most_magnitudes = [
        {'key': f'm{number}', 'name': '등급', 'count': 10, 'sides': 100} for number in range(RULESET_MAX_MAGNITUDES)
    ]

    ruleset = Ruleset.model_validate(
        rules(
            abilities=most_abilities,
            difficulties=most_difficulties,
            default_difficulty='d0',
            score_min=5,
            score_max=5,
            magnitudes=most_magnitudes,
            hp_ability='a0',
            # 점수가 5 하나뿐인 규칙이다. SRD5 의 값표(8~15)도, 주사위로 나오는 점수(3~18)도 맞지 않는다
            point_buy=None,
            score_roll=None,
            # 부상의 효과는 SRD5 의 능력(근력 …)을 가리킨다. 능력이 다른 규칙이라 부상을 뺀다
            **NO_INJURIES,
        )
    )

    assert len(ruleset.abilities) == RULESET_MAX_ABILITIES
    assert len(ruleset.difficulties) == RULESET_MAX_DIFFICULTIES
    assert len(ruleset.magnitudes) == RULESET_MAX_MAGNITUDES


def test_no_ability_has_to_touch_hp():
    ruleset = Ruleset.model_validate(rules(hp_ability=None))

    # 능력치가 HP 에 닿지 않는 규칙도 된다
    assert ruleset.hp_ability is None


def test_a_ruleset_must_say_whether_an_ability_touches_hp():
    document = SRD5.model_dump(mode='json')
    del document['hp_ability']

    # "닿지 않는다"(None)와 "적지 않았다"는 다르다. 적지 않은 문서는 규칙으로 읽히지 않는다
    with pytest.raises(ValidationError):
        Ruleset.model_validate(document)


def test_the_built_in_template_buys_scores_with_27_points():
    point_buy = SRD5.point_buy

    assert point_buy.budget == 27
    assert {entry.score: entry.cost for entry in point_buy.costs} == {
        8: 0,
        9: 1,
        10: 2,
        11: 3,
        12: 4,
        13: 5,
        14: 7,
        15: 9,
    }


def test_a_ruleset_may_have_no_point_buy():
    ruleset = Ruleset.model_validate(rules(point_buy=None))

    assert ruleset.point_buy is None


def test_a_ruleset_must_say_whether_it_has_point_buy():
    document = SRD5.model_dump(mode='json')
    del document['point_buy']

    # "점수제가 없다"(None)와 "적지 않았다"는 다르다. 적지 않은 문서는 규칙으로 읽히지 않는다
    with pytest.raises(ValidationError):
        Ruleset.model_validate(document)


def test_the_costs_need_not_follow_the_scores():
    # 값이 점수에 비례하지 않아도 되고, 살 수 있는 점수가 이어져 있지 않아도 된다. 제작자가 정하는 값이다
    costs = [{'score': 6, 'cost': 0}, {'score': 12, 'cost': 1}, {'score': 18, 'cost': 10}]

    ruleset = Ruleset.model_validate(rules(point_buy={'budget': 12, 'costs': costs}))

    assert [entry.score for entry in ruleset.point_buy.costs] == [6, 12, 18]


def test_the_most_costs_are_allowed():
    costs = [{'score': 5, 'cost': 0}]
    most = [{'score': number + 1, 'cost': number} for number in range(RULESET_MAX_POINT_COSTS)]

    # 점수의 범위를 바꿨으니 주사위로 정하는 법(3~18)은 뺀다. 여기서 보는 것은 값표의 줄 수다
    narrow = rules(score_min=5, score_max=5, score_roll=None, point_buy={'budget': 1, 'costs': costs})
    wide = rules(score_min=1, score_max=30, point_buy={'budget': 100, 'costs': most})

    one = Ruleset.model_validate(narrow)
    many = Ruleset.model_validate(wide)

    assert len(one.point_buy.costs) == 1
    assert len(many.point_buy.costs) == RULESET_MAX_POINT_COSTS


def test_the_built_in_template_rolls_four_dice_and_keeps_three():
    score_roll = SRD5.score_roll

    assert (score_roll.count, score_roll.sides, score_roll.keep) == (4, 6, 3)


def test_a_ruleset_may_have_no_score_roll():
    ruleset = Ruleset.model_validate(rules(score_roll=None))

    assert ruleset.score_roll is None


def test_a_ruleset_must_say_whether_scores_can_be_rolled():
    document = SRD5.model_dump(mode='json')
    del document['score_roll']

    # "그런 방식이 없다"(None)와 "적지 않았다"는 다르다. 적지 않은 문서는 규칙으로 읽히지 않는다
    with pytest.raises(ValidationError):
        Ruleset.model_validate(document)


@pytest.mark.parametrize(
    'score_roll',
    [
        # 범위의 양 끝에 꼭 맞는 것. 1d20 은 1~20, 2d10 은 2~20
        {'count': 1, 'sides': 20, 'keep': 1},
        {'count': 2, 'sides': 10, 'keep': 2},
        # 많이 굴려 조금만 더한다
        {'count': 10, 'sides': 6, 'keep': 3},
    ],
)
def test_any_roll_that_stays_in_the_score_range_is_allowed(score_roll: dict):
    ruleset = Ruleset.model_validate(rules(score_roll=score_roll))

    assert ruleset.score_roll.keep == score_roll['keep']


def test_the_built_in_template_dies_on_three_failed_death_saves():
    death_save = SRD5.death_save

    assert (death_save.target, death_save.successes, death_save.failures) == (10, 3, 3)


def test_a_ruleset_may_have_no_death_save():
    ruleset = Ruleset.model_validate(rules(death_save=None))

    # 주사위가 캐릭터를 죽이지 않는 규칙도 된다. 쓰러진 캐릭터는 쓰러진 채로 있다
    assert ruleset.death_save is None


def test_a_ruleset_must_say_whether_it_has_a_death_save():
    document = SRD5.model_dump(mode='json')
    del document['death_save']

    # "죽이지 않는다"(None)와 "적지 않았다"는 다르다. 적지 않은 문서는 규칙으로 읽히지 않는다
    with pytest.raises(ValidationError):
        Ruleset.model_validate(document)


@pytest.mark.parametrize(
    'death_save',
    [
        # 주사위의 가장 큰 눈이어야만 성공한다. 가혹하지만 성공할 수는 있다
        {'target': 20, 'successes': 1, 'failures': 1},
        # 늘 성공한다. 쓰러져도 죽지 않는 규칙을 이렇게도 적을 수 있다
        {'target': 1, 'successes': 1, 'failures': 10},
    ],
)
def test_any_death_save_that_can_succeed_is_allowed(death_save: dict):
    ruleset = Ruleset.model_validate(rules(death_save=death_save))

    assert ruleset.death_save.target == death_save['target']


def test_a_ruleset_without_magnitudes_is_not_a_ruleset():
    document = SRD5.model_dump(mode='json')
    del document['magnitudes']

    # 빠진 칸을 기본값으로 채우지 않는다. 옛 문서는 읽기 전에 올린다(마이그레이션, 판의 올려 읽기)
    with pytest.raises(ValidationError):
        Ruleset.model_validate(document)


@pytest.mark.parametrize(
    ('keys', 'expected'),
    [
        ([], []),
        (['str', 'dex'], []),
        (['str', 'dex', 'str'], ['str']),
        # 처음 겹친 순서대로, 한 번씩만
        (['b', 'a', 'a', 'b', 'a'], ['a', 'b']),
    ],
)
def test_finds_the_keys_that_appear_twice(keys: list[str], expected: list[str]):
    assert find_duplicates(keys) == expected
