# trpg-server/app/engine/check.py

"""
판정. 능력치의 점수와 난이도, 주사위 한 번으로 성공과 실패를 정한다.

계산은 규칙의 굴림 방식(Ruleset.roll.style, #404)에 따라 둘이다.
  - over: 주사위의 합에 보정을 더한 값이 난이도의 목표값 이상이면 성공이다
  - under: 주사위의 합이 기량(능력치의 점수 + 난이도의 값 + 무기 - 부상) 이하이면 성공이다
부상이 있으면 보정이 깎이거나, 주사위를 두 번 굴려 나쁜 합을 쓴다(불리함, app/engine/injury.py).
공격은 맞서는 굴림(#254, resolve_opposed)으로 가를 수 있다. 받는 쪽도 굴려, 공격하는 쪽이 더 잘 굴려야 맞는다.
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


def known_difficulty(ruleset: Ruleset, key: str | None) -> Difficulty:
    """규칙에 있다고 확인한 난이도(find_fault, 규칙의 검사). 없으면 부른 쪽의 버그라 LookupError 다."""
    difficulty = find_difficulty(ruleset, key)
    if difficulty is None:
        raise LookupError(f'규칙에 없는 난이도입니다: {key}')
    return difficulty


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


@dataclass(frozen=True)
class Side:
    """
    맞서는 굴림(#254)의 한쪽. 능력치의 점수, 능력치 말고 더하는 것(무기, 난이도의 보정, 방어구), 부상의 영향,
    다른 까닭의 불리함(방어하기, 노려 치기)이다.
    """

    score: int
    adjust: int = 0
    hindrance: Hindrance = NO_HINDRANCE
    disadvantage: bool = False


@dataclass(frozen=True)
class Opposed:
    """
    맞서는 굴림 한 번. 공격하는 쪽의 판정(attack)과 받는 쪽의 판정(defense)이다.

    attack.check.success 가 맞았는지다. over 면 공격의 합이 막는 합보다 높아야 맞는다(목표값은 막는 합 + 1).
    under 면 공격이 제 기량 안이고, 막는 쪽이 실패했거나 공격의 여유가 더 커야 맞는다(같으면 막는다).
    defense.check.success 는 막는 쪽이 제 굴림에 성공했는지다(under 의 기량 안, over 는 공격을 막았는지).
    """

    attack: HinderedCheck
    defense: HinderedCheck


def difficulty_shift(ruleset: Ruleset, difficulty: Difficulty) -> int:
    """
    맞서는 굴림에서 공격의 난이도가 공격하는 쪽에 더하는 값. 기본 난이도를 0 으로, 목표값의 차이만큼이다.

    쉬우면 더하고(보통 15 → 쉬움 10 이면 +5), 어려우면 뺀다. under 면 규칙의 shifts 를 쓴다(기량에 더하는 값).
    """
    if ruleset.roll.style == RollStyle.UNDER:
        return skill_shift(ruleset, difficulty)
    base = find_difficulty(ruleset, None)
    return 0 if base is None else base.target - difficulty.target


def roll_side(ruleset: Ruleset, dice: Dice, side: Side) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """한쪽의 주사위를 굴린다. 불리하면 두 번 굴려 나쁜 것을 쓴다. (쓴 눈들, 굴린 합들)이다."""
    pools = roll_for_check(ruleset, dice, side.hindrance.disadvantage or side.disadvantage)
    rolls = tuple(sum(pool) for pool in pools)
    return pools[rolls.index(worse(ruleset, rolls))], rolls


def side_numbers(ruleset: Ruleset, side: Side, faces: tuple[int, ...]) -> tuple[int, int, int]:
    """한쪽의 (보정, 합, 기량). over 의 합은 눈 + 점수의 보정 + 더하는 것이고, under 의 기량은 점수 + 더하는 것이다."""
    adjust = side.adjust - side.hindrance.penalty
    if ruleset.roll.style == RollStyle.UNDER:
        return adjust, sum(faces), side.score + adjust
    modifier = modifier_of(ruleset, side.score) + adjust
    return modifier, sum(faces) + modifier, 0


def attack_lands(ruleset: Ruleset, attack: tuple[int, int, int], defense: tuple[int, int, int]) -> bool:
    """
    공격이 맞았는가. 모양은 side_numbers 의 (보정, 합, 기량)이다.

    over 는 공격의 합 > 막는 합. under 는 공격이 기량 안이고, 막는 쪽이 기량 밖이거나 공격의 여유가 더 크다.
    """
    if ruleset.roll.style != RollStyle.UNDER:
        return attack[1] > defense[1]
    attack_margin, defense_margin = attack[2] - attack[1], defense[2] - defense[1]
    # 막는 쪽이 기량 밖이면 여유가 음수라, 기량 안의 공격은 늘 더 크다
    return attack_margin >= 0 and attack_margin > defense_margin


def opposed_check(
    ruleset: Ruleset, numbers: tuple[int, int, int], faces: tuple[int, ...], target: int, success: bool
) -> Check:
    """맞서는 굴림의 한쪽을 판정의 모양(Check)으로 적는다. 목표값은 부르는 쪽이 정한다."""
    modifier, total, skill = numbers
    style = ruleset.roll.style
    return Check(
        roll=sum(faces),
        modifier=modifier,
        total=total,
        target=skill if style == RollStyle.UNDER else target,
        success=success,
        style=style.value,
        faces=faces,
    )


def resolve_opposed(ruleset: Ruleset, attack: Side, defense: Side, dice: Dice) -> Opposed:
    """
    맞서는 굴림을 한다(#254). 공격하는 쪽을 먼저, 받는 쪽을 그다음에 굴린다.

    over 에서 공격의 목표값은 막는 합 + 1 이고, 막는 쪽의 목표값은 공격의 합이다(같으면 막는다).
    under 에서 목표값은 각자의 기량이다. 맞았는지는 attack_lands 가 정한다.
    """
    attack_faces, attack_rolls = roll_side(ruleset, dice, attack)
    defense_faces, defense_rolls = roll_side(ruleset, dice, defense)
    attack_numbers = side_numbers(ruleset, attack, attack_faces)
    defense_numbers = side_numbers(ruleset, defense, defense_faces)
    hit = attack_lands(ruleset, attack_numbers, defense_numbers)
    held = defense_numbers[2] - defense_numbers[1] >= 0 if ruleset.roll.style == RollStyle.UNDER else not hit
    attack_check = opposed_check(ruleset, attack_numbers, attack_faces, defense_numbers[1] + 1, hit)
    defense_check = opposed_check(ruleset, defense_numbers, defense_faces, attack_numbers[1], held)
    return Opposed(
        attack=HinderedCheck(check=attack_check, rolls=attack_rolls, hindrance=attack.hindrance),
        defense=HinderedCheck(check=defense_check, rolls=defense_rolls, hindrance=defense.hindrance),
    )
