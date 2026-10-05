# game-server/tests/test_sheet.py

"""
캐릭터 시트의 모양과, 시트가 규칙에 맞는지 보는 함수(app/engine/sheet.py)를 검증한다.

DB 도 HTTP 도 쓰지 않는다.
"""

import pytest
from pydantic import ValidationError

from app.engine.ruleset import Ruleset
from app.engine.sheet import SHEET_MAX_HP, Sheet, fits, has_exact_abilities, has_scores_in_range
from app.engine.templates import SRD5
from tests.sheets import SHEET, make_sheet

# 능력치가 둘뿐이고 점수가 0~5 인 규칙. SRD5 와 다른 규칙에서도 같은 함수가 도는지 본다
SMALL_RULES = Ruleset.model_validate(
    {
        **SRD5.model_dump(mode='json'),
        'abilities': [{'key': 'body', 'name': '몸'}, {'key': 'mind', 'name': '마음'}],
        'score_min': 0,
        'score_max': 5,
    }
)


def sheet(document: dict) -> Sheet:
    return Sheet.model_validate(document)


# --- 모양 ---


def test_reads_a_sheet():
    read = sheet(make_sheet(str=16, max_hp=12))

    assert read.abilities['str'] == 16
    assert read.abilities['dex'] == 10
    assert read.max_hp == 12


@pytest.mark.parametrize(
    'document',
    [
        {'abilities': {'str': 10}},
        {'max_hp': 10},
        {'abilities': {'str': 10}, 'max_hp': 0},
        {'abilities': {'str': 10}, 'max_hp': SHEET_MAX_HP + 1},
        {'abilities': {'str': -1}, 'max_hp': 10},
        {'abilities': {'Str': 10}, 'max_hp': 10},
        {'abilities': {'str': 10}, 'max_hp': 10, 'hp': 3},
    ],
)
def test_rejects_a_sheet_with_a_bad_shape(document: dict):
    with pytest.raises(ValidationError):
        sheet(document)


def test_a_sheet_with_no_abilities_has_a_good_shape():
    # 모양은 맞다. 능력치가 하나도 없는 규칙은 없으니 어느 규칙에도 맞지 않을 뿐이다
    empty = sheet({'abilities': {}, 'max_hp': SHEET_MAX_HP})

    assert not fits(SRD5, empty)


# --- 규칙에 맞는가 ---


def test_a_sheet_with_every_ability_in_range_fits():
    assert fits(SRD5, sheet(SHEET))
    # 범위의 양 끝도 된다
    assert fits(SRD5, sheet(make_sheet(str=1, dex=20)))


@pytest.mark.parametrize(
    'abilities',
    [
        # 하나가 빠졌다
        {'str': 10, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10},
        # 규칙에 없는 것이 하나 더 있다
        {**SHEET['abilities'], 'luck': 10},
        # 수는 같지만 하나가 다른 것이다
        {'str': 10, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10, 'luck': 10},
    ],
)
def test_a_sheet_must_have_exactly_the_abilities_of_the_rules(abilities: dict):
    wrong = sheet({'abilities': abilities, 'max_hp': 10})

    assert not has_exact_abilities(SRD5, wrong)
    assert not fits(SRD5, wrong)


@pytest.mark.parametrize('scores', [{'str': 0}, {'str': 21}, {'cha': 1000}])
def test_a_score_outside_the_range_does_not_fit(scores: dict):
    wrong = sheet(make_sheet(**scores))

    assert has_exact_abilities(SRD5, wrong)
    assert not has_scores_in_range(SRD5, wrong)
    assert not fits(SRD5, wrong)


def test_fitting_depends_on_the_rules():
    small = sheet({'abilities': {'body': 5, 'mind': 0}, 'max_hp': 3})

    # 같은 시트가 한 규칙에는 맞고 다른 규칙에는 안 맞는다. 규칙을 인자로 받기 때문이다
    assert fits(SMALL_RULES, small)
    assert not fits(SRD5, small)
    assert not fits(SMALL_RULES, sheet(SHEET))
    assert not fits(SMALL_RULES, sheet({'abilities': {'body': 6, 'mind': 0}, 'max_hp': 3}))
