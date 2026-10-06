# game-server/tests/test_point_buy.py

"""
점수제의 계산(app/engine/point_buy.py)을 검증한다.

DB 도 HTTP 도 쓰지 않는다.
"""

import pytest

from app.engine.point_buy import affordable, cost_of, spent
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5

POINT_BUY = SRD5.point_buy


def scores(**changes: int) -> dict[str, int]:
    """모든 능력치가 8 인 점수에서 몇 개만 바꾼 것. 8 은 SRD5 의 점수제에서 값이 0 이다."""
    return {'str': 8, 'dex': 8, 'con': 8, 'int': 8, 'wis': 8, 'cha': 8, **changes}


def rules(**changes) -> Ruleset:
    """SRD5 템플릿에서 몇 칸만 바꾼 규칙."""
    return Ruleset.model_validate({**SRD5.model_dump(mode='json'), **changes})


# 능력치가 둘뿐이고, 살 수 있는 점수가 띄엄띄엄 있고, 값이 점수에 비례하지 않는 규칙.
# SRD5 와 다른 규칙에서도 같은 함수가 도는지 본다
ODD_RULES = rules(
    abilities=[{'key': 'body', 'name': '몸'}, {'key': 'mind', 'name': '마음'}],
    hp_ability='body',
    point_buy={'budget': 10, 'costs': [{'score': 6, 'cost': 0}, {'score': 12, 'cost': 3}, {'score': 18, 'cost': 10}]},
)


# --- 점수 하나의 값 ---


@pytest.mark.parametrize(('score', 'cost'), [(8, 0), (9, 1), (10, 2), (11, 3), (12, 4), (13, 5), (14, 7), (15, 9)])
def test_the_cost_of_a_score_comes_from_the_table(score: int, cost: int):
    assert cost_of(POINT_BUY, score) == cost


@pytest.mark.parametrize('score', [7, 16, 20, 1, 0])
def test_a_score_that_is_not_in_the_table_cannot_be_bought(score: int):
    # 규칙의 점수 범위(1~20) 안이어도 값표에 없으면 살 수 없다
    assert cost_of(POINT_BUY, score) is None


# --- 든 값의 합 ---


def test_the_lowest_scores_cost_nothing():
    assert spent(POINT_BUY, scores()) == 0


def test_the_costs_add_up():
    # 15, 14, 13, 12, 10, 8 은 9 + 7 + 5 + 4 + 2 + 0 = 27 이다
    abilities = {'str': 15, 'dex': 14, 'con': 13, 'int': 12, 'wis': 10, 'cha': 8}

    assert spent(POINT_BUY, abilities) == 27


def test_one_score_that_cannot_be_bought_spoils_the_sum():
    # 살 수 있는 것만 더해서 싸게 알려 주지 않는다
    assert spent(POINT_BUY, scores(str=16)) is None
    assert spent(POINT_BUY, scores(cha=7)) is None


# --- 살 수 있는가 ---


@pytest.mark.parametrize(
    'abilities',
    [
        {'str': 15, 'dex': 14, 'con': 13, 'int': 12, 'wis': 10, 'cha': 8},
        {'str': 15, 'dex': 15, 'con': 15, 'int': 8, 'wis': 8, 'cha': 8},
        {'str': 13, 'dex': 13, 'con': 13, 'int': 12, 'wis': 12, 'cha': 12},
    ],
)
def test_scores_that_cost_exactly_the_budget_are_affordable(abilities: dict[str, int]):
    assert spent(POINT_BUY, abilities) == POINT_BUY.budget
    assert affordable(SRD5, abilities)


def test_the_budget_need_not_be_used_up():
    assert affordable(SRD5, scores())
    assert affordable(SRD5, scores(str=15))


def test_one_point_over_the_budget_is_too_much():
    # 15, 15, 15 는 27 이다. 하나를 더 사면 넘는다
    abilities = {'str': 15, 'dex': 15, 'con': 15, 'int': 9, 'wis': 8, 'cha': 8}

    assert spent(POINT_BUY, abilities) == 28
    assert not affordable(SRD5, abilities)


@pytest.mark.parametrize('changes', [{'str': 16}, {'str': 7}, {'str': 20}, {'cha': 1}])
def test_scores_outside_the_table_are_not_affordable(changes: dict[str, int]):
    # 총점이 남아도 값표에 없는 점수는 살 수 없다
    assert not affordable(SRD5, scores(**changes))


def test_nothing_is_affordable_when_the_rules_have_no_point_buy():
    assert not affordable(rules(point_buy=None), scores())


# --- 다른 규칙 ---


def test_another_ruleset_uses_its_own_table():
    assert affordable(ODD_RULES, {'body': 18, 'mind': 6})
    assert affordable(ODD_RULES, {'body': 12, 'mind': 12})
    # 18 과 12 는 10 + 3 = 13 이다. 총점 10 을 넘는다
    assert not affordable(ODD_RULES, {'body': 18, 'mind': 12})
    # SRD5 에서는 살 수 있는 점수(8)가 이 규칙의 값표에는 없다
    assert not affordable(ODD_RULES, {'body': 8, 'mind': 6})


def test_the_budget_decides_and_not_the_code():
    generous = rules(point_buy={**SRD5.model_dump(mode='json')['point_buy'], 'budget': 54})
    all_fifteens = scores(str=15, dex=15, con=15, int=15, wis=15, cha=15)

    # 모두 15 는 54 다. SRD5 에서는 못 사고, 총점을 54 로 바꾼 규칙에서는 산다
    assert not affordable(SRD5, all_fifteens)
    assert affordable(generous, all_fifteens)
