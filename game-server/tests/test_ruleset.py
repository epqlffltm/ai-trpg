# game-server/tests/test_ruleset.py

"""
규칙의 모양(app/engine/ruleset.py)과 내장 템플릿(app/engine/templates.py)을 검증한다.

DB 도 HTTP 도 쓰지 않는다. 엔진의 코드는 값을 받아 값을 돌려주므로 그대로 불러 본다.
"""

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.engine.ruleset import RULESET_MAX_ABILITIES, RULESET_MAX_DIFFICULTIES, Ruleset, find_duplicates
from app.engine.templates import DEFAULT_TEMPLATE, SRD5, TEMPLATES, Template, from_template

MIGRATIONS = Path(__file__).parent.parent / 'migrations' / 'versions'


def rules(**changes) -> dict:
    """SRD5 템플릿의 문서에서 몇 칸만 바꾼 것. 틀린 규칙을 만들어 볼 때 쓴다."""
    document = SRD5.model_dump(mode='json')
    document.update(changes)
    return document


def load_backfill_rules() -> dict:
    """
    룰북에 규칙 칸을 더한 마이그레이션이 옛 룰북에 채워 넣은 값을 읽는다.

    파일 이름 앞의 번호는 만들 때마다 다르다. 뒤의 이름으로 찾는다.
    """
    (path,) = MIGRATIONS.glob('*_rulebook_rules.py')
    spec = importlib.util.spec_from_file_location('rulebook_rules_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RULES


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
    # 옛 판을 읽을 때 SRD5 를 "그때의 규칙"으로 쓴다(snapshot.upgrade_from_3).
    # 그러니 SRD5 의 값은 마이그레이션이 채운 값과 늘 같아야 한다. 템플릿을 고치면 이 테스트가 깨진다
    assert load_backfill_rules() == SRD5.model_dump(mode='json')


def test_a_ruleset_cannot_be_changed_after_it_is_made():
    with pytest.raises(ValidationError):
        SRD5.die = 6
    # 목록도 못 고친다. tuple 이라 더하는 메서드가 없다
    assert isinstance(SRD5.abilities, tuple)
    assert isinstance(SRD5.difficulties, tuple)


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

    ruleset = Ruleset.model_validate(
        rules(
            abilities=most_abilities, difficulties=most_difficulties, default_difficulty='d0', score_min=5, score_max=5
        )
    )

    assert len(ruleset.abilities) == RULESET_MAX_ABILITIES
    assert len(ruleset.difficulties) == RULESET_MAX_DIFFICULTIES


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
