# game-server/app/engine/score_roll.py

"""
능력치의 점수를 주사위로 정하는 계산.

굴리는 법은 규칙에서 온다(Ruleset.score_roll). 주사위 몇 개를 굴려 높은 것 몇 개를 더하는지.
점수 하나를 그렇게 정하고, 능력치의 수만큼 되풀이한다.

굴려서 나온 것은 "점수의 묶음"이다. 어느 점수를 어느 능력치에 놓을지는 플레이어가 정한다.
그래서 놓은 결과를 볼 때는 순서를 보지 않고, 굴린 점수를 남김없이 한 번씩 썼는지만 본다(uses_exactly).

주사위는 밖에서 받는다(app/engine/dice.py). 여기의 함수는 DB 도 HTTP 도 모른다.
"""

from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.ruleset import Ruleset, ScoreRoll


@dataclass(frozen=True)
class RolledScore:
    """주사위로 정한 점수 하나. 굴린 눈을 모두 남긴다. 어떻게 나온 점수인지 보여 줄 수 있어야 한다."""

    # 굴린 눈. 굴린 순서 그대로다. 버린 것도 들어 있다
    dice: tuple[int, ...]
    # 높은 것부터 정해진 개수를 더한 값
    score: int


def keep_highest(dice: tuple[int, ...], keep: int) -> int:
    """굴린 눈에서 높은 것부터 keep 개를 더한다."""
    return sum(sorted(dice, reverse=True)[:keep])


def roll_score(score_roll: ScoreRoll, dice: Dice) -> RolledScore:
    """점수 하나를 굴린다."""
    rolled = tuple(dice.roll(score_roll.sides) for _ in range(score_roll.count))
    return RolledScore(dice=rolled, score=keep_highest(rolled, score_roll.keep))


def roll_scores(ruleset: Ruleset, dice: Dice) -> list[RolledScore] | None:
    """
    이 규칙의 능력치의 수만큼 점수를 굴린다. 규칙에 굴리는 법이 없으면 None.

    굴리는 법이 없으면 주사위를 건드리지 않는다.
    """
    if ruleset.score_roll is None:
        return None
    return [roll_score(ruleset.score_roll, dice) for _ in ruleset.abilities]


def uses_exactly(scores: list[int], abilities: dict[str, int]) -> bool:
    """
    능력치에 놓은 점수가 굴린 점수를 남김없이, 한 번씩만 쓴 것인가.

    어느 능력치에 놓았는지는 보지 않는다. 그것은 플레이어가 정한다.
    같은 점수가 두 번 나왔으면 두 번 쓸 수 있고, 한 번 나왔으면 한 번만 쓸 수 있다.
    """
    return sorted(scores) == sorted(abilities.values())
