# trpg-server/app/engine/check.py

"""
판정. 능력치의 점수와 난이도, 주사위 한 번으로 성공과 실패를 정한다.

계산은 규칙의 굴림 방식(Ruleset.roll.style, #404)에 따라 둘이다.
  - over: 주사위의 합에 보정을 더한 값이 난이도의 목표값 이상이면 성공이다
  - under: 주사위의 합이 기량(능력치의 점수 + 난이도의 값 + 무기 - 부상) 이하이면 성공이다
부상이 있으면 보정이 깎이거나, 주사위를 두 번 굴려 나쁜 합을 쓴다(불리함, app/engine/injury.py).
숫자(주사위의 면 수와 개수, 보정을 구하는 값, 목표값)는 모두 규칙에서 온다. 규칙이 달라져도 이 코드는 그대로다.

여기의 함수는 DB 도 HTTP 도 모른다. 주사위만 밖에서 받는다. 같은 눈을 주면 같은 결과가 나온다.
"""

from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.injury import NO_HINDRANCE, Hindrance
from app.engine.rolls import passes, roll_pool, worse
from app.engine.ruleset import Ability, Difficulty, RollStyle, Ruleset


@dataclass(frozen=True)
class Check:
    """
    판정 한 번의 결과. 어떻게 그 결과가 나왔는지를 숫자로 다 담는다.

    성공했는지만 담지 않는다. 기록에 남기고 화면에 보여 주려면 과정이 있어야 한다.
    under(#404)에서는 보정이 눈이 아니라 기량에 더해진다. modifier 는 점수에 더한 값 전부(난이도의 값, 무기, 부상)이고,
    total 은 눈 그대로, target 은 기량(점수 + modifier)이다. 성공은 total ≤ target 이다.
    """

    # 주사위의 눈(여럿을 굴리면 그 합)
    roll: int
    # over: 능력치의 점수에서 나온 보정. under: 점수에 더한 값
    modifier: int
    # over: 눈에 보정을 더한 값. under: 눈
    total: int
    # over: 난이도의 목표값. under: 기량
    target: int
    success: bool
    # 성공을 가른 방식(RollStyle 의 값)
    style: str
    # 쓴 굴림의 눈들. 더하면 roll 이다
    faces: tuple[int, ...]


def miss_by(check: Check) -> int:
    """목표에 모자란 양. 성공했으면 0 이하다. over 면 목표 - 합, under 면 눈 - 기량이다."""
    if check.style == RollStyle.UNDER:
        return check.total - check.target
    return check.target - check.total


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
    부상의 영향을 받은 판정 한 번. 판정의 결과와, 굴린 합들(불리함이면 둘), 영향을 준 것.

    판정의 눈(check.roll)은 굴린 합 중 쓴 것이고, 보정(check.modifier)은 부상이 깎은 뒤의 것이다.
    주사위를 하나 굴리는 규칙이면 합은 눈 그대로다.
    """

    check: Check
    rolls: tuple[int, ...]
    hindrance: Hindrance


def roll_for_check(ruleset: Ruleset, dice: Dice, disadvantage: bool) -> tuple[tuple[int, ...], ...]:
    """판정의 주사위를 굴린다. 불리하면 두 번 굴린다. 한 번마다 규칙의 개수만큼의 눈이다. 굴린 순서대로 돌려준다."""
    return tuple(roll_pool(ruleset, dice) for _ in range(2 if disadvantage else 1))


def harder_by(ruleset: Ruleset, difficulty: Difficulty) -> int:
    """
    난이도가 규칙의 그 단계보다 오른 양. 부르는 쪽이 목표값을 올려 넘긴 것이다(노려 치기, 방어, 훔치기의 까닭들).

    under 에서는 오른 만큼 기량이 깎인다. 규칙에 없는 단계면 0 이다.
    """
    base = find_difficulty(ruleset, difficulty.key)
    return 0 if base is None else difficulty.target - base.target


def skill_shift(ruleset: Ruleset, difficulty: Difficulty) -> int:
    """under 에서 난이도가 기량에 더하는 값. 규칙의 shifts 에서 그 단계의 것에, 오른 만큼을 뺀다."""
    return ruleset.roll.shifts.get(difficulty.key, 0) - harder_by(ruleset, difficulty)


def judge(ruleset: Ruleset, score: int, difficulty: Difficulty, faces: tuple[int, ...], adjust: int) -> Check:
    """
    쓸 굴림의 눈들로 판정을 정한다. adjust 는 능력치 말고 더하는 것 전부다(무기의 보정 - 부상).

    over 는 합 + 점수의 보정 + adjust 를 난이도의 목표값과, under 는 합을 점수 + 난이도의 값 + adjust 와 견준다.
    """
    roll = sum(faces)
    if ruleset.roll.style == RollStyle.UNDER:
        modifier = skill_shift(ruleset, difficulty) + adjust
        total, target = roll, score + modifier
    else:
        modifier = modifier_of(ruleset, score) + adjust
        total, target = roll + modifier, difficulty.target
    return Check(
        roll=roll,
        modifier=modifier,
        total=total,
        target=target,
        success=passes(ruleset, total, target),
        style=ruleset.roll.style.value,
        faces=faces,
    )


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
    bonus: int = 0,
) -> HinderedCheck:
    """
    부상의 영향을 받는 판정 한 번을 한다. 주사위를 한 번(불리하면 두 번) 굴린다.

    score 는 판정에 쓰는 능력치의 점수, difficulty 는 규칙에서 찾은 난이도의 단계다. 목표값을 올려 넘기면
    그만큼 어렵다(under 에서는 기량이 그만큼 깎인다, harder_by).
    hindrance 는 입은 부상이 이 판정에 주는 것이다. 보정을 깎고, 불리하면 나쁜 합을 쓴다(worse).
    forced_disadvantage 는 부상 말고 다른 까닭(노려 치기)으로 불리한가다. 불리함은 겹쳐도 두 번만 굴린다.
    bonus 는 능력치 말고 보정에 더하는 것이다(무기의 공격 보정, #276). 보정(modifier)에 함께 든다.
    돌려준 것의 hindrance 는 받은 부상의 것 그대로다. 다른 까닭의 불리함은 거기에 섞지 않는다.
    """
    pools = roll_for_check(ruleset, dice, hindrance.disadvantage or forced_disadvantage)
    rolls = tuple(sum(pool) for pool in pools)
    used = pools[rolls.index(worse(ruleset, rolls))]
    check = judge(ruleset, score, difficulty, used, bonus - hindrance.penalty)
    return HinderedCheck(check=check, rolls=rolls, hindrance=hindrance)
