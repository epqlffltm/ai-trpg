# game-server/app/engine/point_buy.py

"""
점수제의 계산. 플레이어가 고른 능력치의 점수가 정해진 총점 안에서 살 수 있는 것인지 본다.

값은 모두 규칙에서 온다(Ruleset.point_buy). 총점이 얼마인지, 어느 점수를 살 수 있는지, 점수마다 값이 얼마인지.
규칙이 달라져도 이 코드는 그대로다.

여기의 함수는 DB 도 HTTP 도 모른다.
"""

from app.engine.ruleset import PointBuy, Ruleset


def cost_of(point_buy: PointBuy, score: int) -> int | None:
    """이 점수를 사는 데 드는 값. 값표에 없는 점수면 None. 살 수 없는 점수다."""
    return next((entry.cost for entry in point_buy.costs if entry.score == score), None)


def spent(point_buy: PointBuy, abilities: dict[str, int]) -> int | None:
    """
    이 점수들을 사는 데 드는 값을 모두 더한다. 살 수 없는 점수가 하나라도 있으면 None.

    능력치가 규칙의 것인지는 여기서 보지 않는다(app/engine/sheet.py 의 abilities_fit).
    """
    costs = [cost_of(point_buy, score) for score in abilities.values()]
    if any(cost is None for cost in costs):
        return None
    return sum(costs)


def affordable(ruleset: Ruleset, abilities: dict[str, int]) -> bool:
    """
    이 점수들을 이 규칙의 점수제로 살 수 있는가.

    규칙에 점수제가 없으면 살 수 없다. 살 수 없는 점수가 있어도, 총점을 넘어도 살 수 없다.
    총점을 다 쓰지 않아도 된다.
    """
    if ruleset.point_buy is None:
        return False
    total = spent(ruleset.point_buy, abilities)
    return total is not None and total <= ruleset.point_buy.budget
