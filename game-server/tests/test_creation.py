# game-server/tests/test_creation.py

"""
플레이어가 능력치를 정한 캐릭터의 시트를 만드는 계산(app/engine/creation.py)을 검증한다.

DB 도 HTTP 도 쓰지 않는다.
"""

import pytest

from app.engine.creation import build_sheet, hp_bonus, max_hp_for
from app.engine.ruleset import Ruleset
from app.engine.sheet import Sheet, abilities_fit
from app.engine.templates import SRD5


def scores(**changes: int) -> dict[str, int]:
    """모든 능력치가 10 인 점수에서 몇 개만 바꾼 것."""
    return {'str': 10, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10, 'cha': 10, **changes}


def rules(**changes) -> Ruleset:
    """SRD5 템플릿에서 몇 칸만 바꾼 규칙."""
    return Ruleset.model_validate({**SRD5.model_dump(mode='json'), **changes})


# 능력치가 HP 에 닿지 않는 규칙
NO_HP_ABILITY = rules(hp_ability=None)
# 근력이 HP 에 닿는 규칙
STRENGTH_FOR_HP = rules(hp_ability='str')


# --- 능력치에서 HP 에 더해지는 값 ---


@pytest.mark.parametrize(('con', 'bonus'), [(10, 0), (14, 2), (15, 2), (20, 5), (9, -1), (1, -5)])
def test_the_bonus_is_the_modifier_of_the_ability_the_rules_name(con: int, bonus: int):
    assert hp_bonus(SRD5, scores(con=con)) == bonus


def test_other_abilities_do_not_touch_hp():
    assert hp_bonus(SRD5, scores(str=20, dex=20)) == 0


def test_which_ability_touches_hp_comes_from_the_rules():
    strong = scores(str=18, con=8)

    assert hp_bonus(SRD5, strong) == -1
    assert hp_bonus(STRENGTH_FOR_HP, strong) == 4
    assert hp_bonus(NO_HP_ABILITY, strong) == 0


# --- 최대 HP ---


def test_max_hp_is_the_base_plus_the_bonus():
    assert max_hp_for(SRD5, scores(con=14), base=10, cap=20) == 12
    assert max_hp_for(SRD5, scores(con=8), base=10, cap=20) == 9


@pytest.mark.parametrize(('con', 'expected'), [(10, 10), (12, 11), (14, 12), (16, 12), (20, 12)])
def test_max_hp_never_passes_the_cap(con: int, expected: int):
    # 기준 10, 상한 12. 건강이 아무리 높아도 12 에서 멈춘다
    assert max_hp_for(SRD5, scores(con=con), base=10, cap=12) == expected


def test_a_cap_equal_to_the_base_lets_the_bonus_only_take_away():
    assert max_hp_for(SRD5, scores(con=20), base=10, cap=10) == 10
    assert max_hp_for(SRD5, scores(con=6), base=10, cap=10) == 8


def test_max_hp_never_drops_below_one():
    # 기준 3 에 보정 -5. 0 이하가 되면 시작하자마자 쓰러진 캐릭터가 된다
    assert max_hp_for(SRD5, scores(con=1), base=3, cap=20) == 1


def test_without_an_hp_ability_max_hp_is_the_base():
    assert max_hp_for(NO_HP_ABILITY, scores(con=20), base=10, cap=20) == 10


# --- 시트 만들기 ---


def test_builds_a_sheet_from_the_scores_a_player_chose():
    chosen = scores(str=15, con=14)

    sheet = build_sheet(SRD5, chosen, base=10, cap=20)

    assert sheet == Sheet(abilities=chosen, max_hp=12)


def test_building_copies_the_scores():
    chosen = scores(con=14)

    sheet = build_sheet(SRD5, chosen, base=10, cap=20)
    chosen['con'] = 1

    # 받은 점수를 나중에 고쳐도 만든 시트는 그대로다
    assert sheet.abilities['con'] == 14


# --- 능력치만 보는 검사 ---


@pytest.mark.parametrize(
    ('chosen', 'ok'),
    [
        (scores(), True),
        (scores(str=1, dex=20), True),
        # 범위 밖
        (scores(str=0), False),
        (scores(str=21), False),
        # 빠진 능력치, 없는 능력치
        ({'str': 10}, False),
        ({**scores(), 'luck': 10}, False),
        ({}, False),
    ],
)
def test_scores_must_fit_the_rules(chosen: dict[str, int], ok: bool):
    assert abilities_fit(SRD5, chosen) is ok
