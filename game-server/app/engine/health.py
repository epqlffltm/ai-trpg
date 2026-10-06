# game-server/app/engine/health.py

"""
HP 를 바꾸는 계산. 피해와 회복, 쓰러짐.

양은 숫자로 받지 않는다. 규칙의 등급(Magnitude)으로 받아 주사위를 굴려 정한다.
HP 는 0 아래로 내려가지 않고 최대를 넘지 않는다. HP 가 0 이면 쓰러진 것이다.

여기의 함수는 DB 도 HTTP 도 모른다. 지금의 HP 를 받아 바뀐 HP 를 돌려준다.
시트를 고치는 것은 부른 쪽의 일이다(app/rounds/service.py).
"""

import enum
from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.ruleset import Magnitude, Ruleset


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


def change_hp(kind: ChangeKind, magnitude: Magnitude, hp: int, max_hp: int, dice: Dice) -> Change:
    """
    HP 를 한 번 바꾼다. 주사위를 굴려 양을 정하고, 바뀐 결과를 돌려준다.

    hp 와 max_hp 는 바뀌는 캐릭터의 지금 HP 와 최대 HP 다. 받은 값을 고치지 않는다.
    """
    rolls = roll_amount(magnitude, dice)
    amount = sum(rolls)
    after = hurt(hp, amount) if kind == ChangeKind.DAMAGE else heal(hp, max_hp, amount)
    return Change(kind=kind, rolls=rolls, amount=amount, before=hp, after=after)
