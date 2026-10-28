# trpg-server/app/engine/health.py

"""
HP 를 바꾸는 계산. 피해와 회복, 쓰러짐.

양은 숫자로 받지 않는다. 규칙의 등급(Magnitude)으로 받아 주사위를 굴려 정한다.
HP 는 0 아래로 내려가지 않고 최대를 넘지 않는다. HP 가 0 이면 쓰러진 것이다.

여기의 함수는 DB 도 HTTP 도 모른다. 지금의 HP 를 받아 바뀐 HP 를 돌려준다.
시트를 고치는 것은 부른 쪽의 일이다(app/rounds/checks.py).
"""

import enum
from dataclasses import dataclass, replace

from app.engine.dice import Dice
from app.engine.ruleset import Magnitude, ResistLevel, Ruleset


class ChangeKind(enum.StrEnum):
    """HP 가 바뀌는 방향."""

    DAMAGE = 'damage'
    RECOVERY = 'recovery'


@dataclass(frozen=True)
class Change:
    """
    HP 가 한 번 바뀐 것. 어떻게 그 값이 됐는지를 다 담는다.

    amount 는 주사위가 정한 양이고, before 와 after 는 실제로 바뀐 HP 다.
    둘의 차이가 amount 보다 작을 수 있다. HP 가 0 이나 최대에 닿으면 거기서 멈춘다.
    """

    kind: ChangeKind
    # 주사위의 눈들. 굴린 순서다
    rolls: tuple[int, ...]
    # 눈을 모두 더한 값
    amount: int
    before: int
    after: int
    # 방어구가 깎은 양(#276). 눈을 더한 값에서 이만큼 빼서 amount 가 됐다. 깎지 않았으면 0 이다
    blocked: int = 0
    # 피해의 성질(#886 ③). 성질이 없는 피해와 회복이면 None 이다
    nature: str | None = None
    # 맞은 쪽이 그 성질을 받은 단계(저항, 면역, 약점). 깎은 뒤의 양에 걸어 amount 가 됐다. 그대로 받았으면 None 이다
    level: ResistLevel | None = None

    @property
    def downed(self) -> bool:
        """이 변화로 HP 가 0 이 됐거나, 0 인 채로 남았는가."""
        return is_downed(self.after)


def is_downed(hp: int) -> bool:
    """쓰러졌는가. HP 가 0 이면 쓰러진 것이다."""
    return hp <= 0


def find_magnitude(ruleset: Ruleset, key: str) -> Magnitude | None:
    """규칙에서 양의 등급을 찾는다. 없으면 None."""
    return next((magnitude for magnitude in ruleset.magnitudes if magnitude.key == key), None)


def roll_amount(magnitude: Magnitude, dice: Dice) -> tuple[int, ...]:
    """등급이 정한 주사위를 굴린다. 눈들을 굴린 순서대로 돌려준다."""
    return tuple(dice.roll(magnitude.sides) for _ in range(magnitude.count))


def hurt(hp: int, amount: int) -> int:
    """피해를 입은 뒤의 HP. 0 아래로 내려가지 않는다."""
    return max(0, hp - amount)


def heal(hp: int, max_hp: int, amount: int) -> int:
    """회복한 뒤의 HP. 최대를 넘지 않는다."""
    return min(max_hp, hp + amount)


@dataclass(frozen=True)
class Nature:
    """피해의 성질(#886 ③)과 맞는 쪽이 그것을 받는 단계. 단계가 None 이면 그대로 받는다."""

    key: str
    level: ResistLevel | None = None


def resist(amount: int, level: ResistLevel | None) -> int:
    """
    피해의 양에 저항의 단계를 건다(#886 ③). 저항은 반(내림), 면역은 0, 약점은 두 배, 없으면 그대로다.
    """
    if level == ResistLevel.IMMUNE:
        return 0
    if level == ResistLevel.RESIST:
        return amount // 2
    if level == ResistLevel.VULNERABLE:
        return amount * 2
    return amount


def change_hp(
    kind: ChangeKind,
    magnitude: Magnitude,
    hp: int,
    max_hp: int,
    dice: Dice,
    cut: int = 0,
    nature: Nature | None = None,
) -> Change:
    """
    HP 를 한 번 바꾼다. 주사위를 굴려 양을 정하고, 바뀐 결과를 돌려준다.

    hp 와 max_hp 는 바뀌는 캐릭터의 지금 HP 와 최대 HP 다. 받은 값을 고치지 않는다.
    cut 은 피해에서 깎을 양이다(방어구, #276). 눈을 더한 값보다 많이 깎지 않는다. 회복에는 쓰지 않는다.
    nature 는 피해의 성질과 맞는 쪽의 단계다(#886 ③). 방어구가 깎은 뒤의 양에 건다. 회복에는 쓰지 않는다.
    """
    rolls = roll_amount(magnitude, dice)
    if kind == ChangeKind.DAMAGE:
        return damage_change(rolls, hp, cut, nature)
    amount = sum(rolls)
    return Change(kind=kind, rolls=rolls, amount=amount, before=hp, after=heal(hp, max_hp, amount))


def damage_change(rolls: tuple[int, ...], hp: int, cut: int, nature: Nature | None) -> Change:
    """굴린 눈으로 피해를 정한다. 방어구가 깎고(cut), 남은 양에 성질의 단계를 건다(#886 ③)."""
    blocked = min(cut, sum(rolls))
    level = nature.level if nature is not None else None
    amount = resist(sum(rolls) - blocked, level)
    key = nature.key if nature is not None else None
    return Change(ChangeKind.DAMAGE, rolls, amount, hp, hurt(hp, amount), blocked, key, level)


# 장난(#803)의 피해가 남기는 HP 의 바닥. 이 아래로 내리지 못한다
PRANK_FLOOR = 1


def spare(change: Change) -> Change:
    """
    장난의 피해(#803). HP 를 PRANK_FLOOR 아래로 내리지 못한 변화를 돌려준다. 받은 변화는 고치지 않는다.

    주사위의 눈과 양(amount)은 그대로다. 실제로 바뀐 HP(after)만 바닥에서 멈춘다. 이미 그 아래였으면(쓰러져 있었으면)
    더 내리지 않는다. 회복은 그대로다.
    """
    if change.kind != ChangeKind.DAMAGE:
        return change
    return replace(change, after=max(change.after, min(change.before, PRANK_FLOOR)))
