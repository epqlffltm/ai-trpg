# game-server/app/engine/check.py

"""
판정. 능력치의 점수와 난이도, 주사위 한 번으로 성공과 실패를 정한다.

계산은 하나다. 주사위의 눈에 보정을 더한 값이 난이도의 목표값 이상이면 성공이다.
부상이 있으면 보정이 깎이거나, 주사위를 두 번 굴려 낮은 눈을 쓴다(불리함, app/engine/injury.py).
숫자(주사위의 면 수, 보정을 구하는 값, 목표값)는 모두 규칙에서 온다. 규칙이 달라져도 이 코드는 그대로다.

여기의 함수는 DB 도 HTTP 도 모른다. 주사위만 밖에서 받는다. 같은 눈을 주면 같은 결과가 나온다.
"""

from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.injury import NO_HINDRANCE, Hindrance
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


@dataclass(frozen=True)
class HinderedCheck:
    """
    부상의 영향을 받은 판정 한 번. 판정의 결과와, 굴린 눈들(불리함이면 둘), 영향을 준 것.

    판정의 눈(check.roll)은 굴린 눈 중 쓴 것이고, 보정(check.modifier)은 부상이 깎은 뒤의 것이다.
    """

    check: Check
    rolls: tuple[int, ...]
    hindrance: Hindrance


def roll_for_check(ruleset: Ruleset, dice: Dice, disadvantage: bool) -> tuple[int, ...]:
    """판정의 주사위를 굴린다. 불리하면 두 번 굴린다. 굴린 순서대로 돌려준다."""
    return tuple(dice.roll(ruleset.die) for _ in range(2 if disadvantage else 1))


def resolve(ruleset: Ruleset, score: int, difficulty: Difficulty, dice: Dice) -> Check:
    """
    판정 한 번을 한다. 주사위를 한 번 굴린다. 부상의 영향이 없는 판정이다.

    score 는 판정에 쓰는 능력치의 점수, difficulty 는 규칙에서 찾은 난이도의 단계다.
    """
    return resolve_hindered(ruleset, score, difficulty, dice, NO_HINDRANCE).check


def resolve_hindered(
    ruleset: Ruleset,
    score: int,
    difficulty: Difficulty,
    dice: Dice,
    hindrance: Hindrance,
    forced_disadvantage: bool = False,
) -> HinderedCheck:
    """
    부상의 영향을 받는 판정 한 번을 한다. 주사위를 한 번(불리하면 두 번) 굴린다.

    score 는 판정에 쓰는 능력치의 점수, difficulty 는 규칙에서 찾은 난이도의 단계다.
    hindrance 는 입은 부상이 이 판정에 주는 것이다. 보정을 깎고, 불리하면 낮은 눈을 쓴다.
    forced_disadvantage 는 부상 말고 다른 까닭(노려 치기)으로 불리한가다. 불리함은 겹쳐도 두 번만 굴린다.
    돌려준 것의 hindrance 는 받은 부상의 것 그대로다. 다른 까닭의 불리함은 거기에 섞지 않는다.
    """
    rolls = roll_for_check(ruleset, dice, hindrance.disadvantage or forced_disadvantage)
    roll = min(rolls)
    modifier = modifier_of(ruleset, score) - hindrance.penalty
    total = roll + modifier
    check = Check(
        roll=roll, modifier=modifier, total=total, target=difficulty.target, success=total >= difficulty.target
    )
    return HinderedCheck(check=check, rolls=rolls, hindrance=hindrance)
