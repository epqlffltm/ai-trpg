# trpg-server/app/engine/rolls.py

"""
규칙의 굴림(#404). 주사위 몇 개를 굴려 더하고, 성공을 어느 쪽으로 가르는지다.

판정, 죽음의 굴림, 되살아나기, 관통과 세이브, 선공을 가르는 굴림이 모두 여기를 거친다.
개수와 방식은 규칙(Ruleset.roll)에서 온다. over 는 합이 목표 이상이면, under 는 합이 기량 이하이면 성공이다.

여기의 함수는 DB 도 HTTP 도 모른다. 주사위만 밖에서 받는다.
"""

from app.engine.dice import Dice
from app.engine.ruleset import RollStyle, Ruleset


def roll_pool(ruleset: Ruleset, dice: Dice) -> tuple[int, ...]:
    """규칙의 주사위를 규칙의 개수만큼 굴린다. 굴린 순서대로 눈들을 돌려준다."""
    return tuple(dice.roll(ruleset.die) for _ in range(ruleset.roll.count))


def passes(ruleset: Ruleset, total: int, target: int) -> bool:
    """굴린 합이 목표에 닿았는가. over 면 합이 목표 이상, under 면 합이 목표(기량) 이하다."""
    if ruleset.roll.style == RollStyle.UNDER:
        return total <= target
    return total >= target


def worse(ruleset: Ruleset, totals: tuple[int, ...]) -> int:
    """여러 번 굴린 합 중 나쁜 것(불리함). over 면 가장 작은 합, under 면 가장 큰 합이다."""
    if ruleset.roll.style == RollStyle.UNDER:
        return max(totals)
    return min(totals)


def better_first(ruleset: Ruleset, total: int) -> int:
    """좋은 합이 앞에 오게 정렬하는 열쇠. over 면 큰 합이, under 면 작은 합이 앞이다."""
    return total if ruleset.roll.style == RollStyle.UNDER else -total
