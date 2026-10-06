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
    Ruleset,
    find_duplicates,
)
from app.engine.templates import DEFAULT_TEMPLATE, SRD5, TEMPLATES, Template, from_template

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

    규칙 칸을 더할 때 채운 값(rulebook_rules)에, 양의 등급을 더할 때 채운 값(rulebook_magnitudes)을 합친다.
    """
    rules = load_migration('rulebook_rules').RULES
    magnitudes = load_migration('rulebook_magnitudes').MAGNITUDES
    return {**rules, 'magnitudes': magnitudes}


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
        )
    )

    assert len(ruleset.abilities) == RULESET_MAX_ABILITIES
    assert len(ruleset.difficulties) == RULESET_MAX_DIFFICULTIES
    assert len(ruleset.magnitudes) == RULESET_MAX_MAGNITUDES


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
