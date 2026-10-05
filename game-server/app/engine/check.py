# game-server/app/engine/check.py

"""
판정. 능력치의 점수와 난이도, 주사위 한 번으로 성공과 실패를 정한다.

계산은 하나다. 주사위의 눈에 보정을 더한 값이 난이도의 목표값 이상이면 성공이다.
숫자(주사위의 면 수, 보정을 구하는 값, 목표값)는 모두 규칙에서 온다. 규칙이 달라져도 이 코드는 그대로다.

여기의 함수는 DB 도 HTTP 도 모른다. 주사위만 밖에서 받는다. 같은 눈을 주면 같은 결과가 나온다.
"""

from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.ruleset import Ability, Difficulty, Ruleset


@dataclass(frozen=True)
class Check:
    """
    판정 한 번의 결과. 어떻게 그 결과가 나왔는지를 숫자로 다 담는다.

    성공했는지만 담지 않는다. 기록에 남기고 화면에 보여 주려면 과정이 있어야 한다.
    """

    # 주사위의 눈
    roll: int
    # 능력치의 점수에서 나온 보정
    modifier: int
    # 눈에 보정을 더한 값
    total: int
    # 난이도의 목표값
    target: int
    success: bool


def find_ability(ruleset: Ruleset, key: str) -> Ability | None:
    """규칙에서 능력치를 찾는다. 없으면 None."""
    return next((ability for ability in ruleset.abilities if ability.key == key), None)


def find_difficulty(ruleset: Ruleset, key: str | None) -> Difficulty | None:
    """
    규칙에서 난이도의 단계를 찾는다. 없으면 None.

    key 를 주지 않으면 규칙의 기본 난이도다. 기본 난이도는 규칙을 만들 때 단계 중 하나임을 확인했다.
    """
    wanted = key if key is not None else ruleset.default_difficulty
    return next((difficulty for difficulty in ruleset.difficulties if difficulty.key == wanted), None)


def modifier_of(ruleset: Ruleset, score: int) -> int:
    """
    능력치의 점수를 보정으로 바꾼다. (점수 - base) // step 이고, 내림한다.

    // 는 음수에서도 아래로 내린다. base 10, step 2 에서 점수 9 는 -1 이다(-0.5 를 내림).
    """
    return (score - ruleset.modifier.base) // ruleset.modifier.step


def resolve(ruleset: Ruleset, score: int, difficulty: Difficulty, dice: Dice) -> Check:
    """
    판정 한 번을 한다. 주사위를 한 번 굴린다.

    score 는 판정에 쓰는 능력치의 점수, difficulty 는 규칙에서 찾은 난이도의 단계다.
    """
    roll = dice.roll(ruleset.die)
    modifier = modifier_of(ruleset, score)
    total = roll + modifier
    return Check(
        roll=roll, modifier=modifier, total=total, target=difficulty.target, success=total >= difficulty.target
    )
