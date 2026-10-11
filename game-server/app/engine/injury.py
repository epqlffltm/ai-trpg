# game-server/app/engine/injury.py

"""
부상의 계산. 부상 표를 언제 굴리는지, 무엇이 나오는지, 입은 부상이 판정에 무엇을 하는지.

부상이 무엇이고 언제 생기는지는 규칙의 데이터다(app/engine/ruleset.py 의 Injury, InjuryTable, InjuryTriggers).
엔진이 집행하는 효과는 셋뿐이다. 보정 깎기, 불리함(두 번 굴려 낮은 눈), 행동 불가.
"그 손을 못 쓴다" 같은 것은 부상의 사실이고, 서술자가 지킨다.

여기의 함수는 DB 도 HTTP 도 모른다. 부상의 이름들과 규칙을 받아 계산만 한다. 주사위만 밖에서 받는다.
"""

import enum
from collections.abc import Iterable
from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.health import Change, ChangeKind
from app.engine.ruleset import EffectKind, Healing, Injury, InjuryTable, Ruleset


class Trigger(enum.StrEnum):
    """부상이 생긴 까닭. 앞의 둘은 부상 표를 굴린 까닭이다."""

    # 한 번의 피해가 최대 HP 의 정한 비율 이상이었다
    BIG_HIT = 'big_hit'
    # 이 피해로 쓰러졌다
    DOWNED = 'downed'
    # 노려 쳐서 그 부상이 확정으로 생겼다. 표를 굴리지 않는다
    CALLED_SHOT = 'called_shot'


@dataclass(frozen=True)
class TableRoll:
    """부상 표를 한 번 굴린 것. injury 는 나온 부상의 이름이다. 부상이 없는 줄이면 None."""

    trigger: Trigger
    roll: int
    injury: str | None


@dataclass(frozen=True)
class Hindrance:
    """
    입은 부상이 판정 하나에 주는 것. 보정을 깎는 양, 불리함, 그리고 영향을 준 부상들의 이름.

    아무 부상도 영향을 주지 않으면 penalty 0, disadvantage False, injuries 빈 것이다.
    """

    penalty: int = 0
    disadvantage: bool = False
    injuries: tuple[str, ...] = ()

    @property
    def any(self) -> bool:
        """판정에 무엇이든 영향을 주는가."""
        return bool(self.injuries)


NO_HINDRANCE = Hindrance()


def find_injury(ruleset: Ruleset, key: str) -> Injury | None:
    """규칙에서 부상을 찾는다. 없으면 None."""
    return next((injury for injury in ruleset.injuries if injury.key == key), None)


def known_injuries(ruleset: Ruleset, keys: Iterable[str]) -> list[Injury]:
    """이름들을 규칙의 부상으로. 규칙에 없는 이름은 뺀다(규칙이 바뀐 판으로 읽을 때). 받은 순서다."""
    return [injury for key in keys if (injury := find_injury(ruleset, key)) is not None]


def trigger_of(ruleset: Ruleset, change: Change, max_hp: int, dead: bool) -> Trigger | None:
    """
    이 HP 의 변화가 부상 표를 굴리게 하는가. 굴리면 그 까닭, 아니면 None.

    피해일 때만, 그리고 대상이 죽지 않았을 때만 굴린다. 쓰러짐(이 피해로 HP 가 0 이 됨)을 큰 타격보다 먼저 본다.
    큰 타격은 주사위가 정한 양(amount)으로 잰다. 이미 HP 가 적어 실제로 덜 깎였어도 큰 한 방은 큰 한 방이다.
    둘이 함께 맞아도 표는 한 번만 굴린다.
    """
    if change.kind != ChangeKind.DAMAGE or dead:
        return None
    triggers = ruleset.injury_triggers
    if triggers.downed and change.before > 0 and change.after == 0:
        return Trigger.DOWNED
    percent = triggers.big_hit_percent
    if percent is not None and change.amount * 100 >= percent * max_hp:
        return Trigger.BIG_HIT
    return None


def row_injury(table: InjuryTable, roll: int) -> str | None:
    """표에서 이 눈이 든 줄의 부상. 표는 모든 눈을 덮는다(InjuryTable 의 검사)."""
    return next(row.injury for row in table.rows if row.low <= roll <= row.high)


def roll_table(table: InjuryTable, trigger: Trigger, dice: Dice) -> TableRoll:
    """부상 표를 한 번 굴린다."""
    roll = dice.roll(table.sides)
    return TableRoll(trigger=trigger, roll=roll, injury=row_injury(table, roll))


def touches(abilities: tuple[str, ...], ability: str) -> bool:
    """효과가 이 능력에 닿는가. 능력을 적지 않은 효과는 모든 능력에 닿는다."""
    return not abilities or ability in abilities


def hindrance_of(injuries: Iterable[Injury], ability: str) -> Hindrance:
    """입은 부상들이 이 능력의 판정에 주는 것을 모은다. 보정 깎기는 더하고, 불리함은 하나라도 있으면 있다."""
    penalty = 0
    disadvantage = False
    names: list[str] = []
    for injury in injuries:
        hits = [effect for effect in injury.effects if effect.kind != EffectKind.NO_ACTIONS]
        hits = [effect for effect in hits if touches(effect.abilities, ability)]
        if not hits:
            continue
        penalty += sum(effect.amount for effect in hits if effect.kind == EffectKind.PENALTY)
        disadvantage = disadvantage or any(effect.kind == EffectKind.DISADVANTAGE for effect in hits)
        names.append(injury.key)
    return Hindrance(penalty=penalty, disadvantage=disadvantage, injuries=tuple(names))


def blocks_actions(injuries: Iterable[Injury]) -> bool:
    """입은 부상 중에 행동을 막는 것이 있는가."""
    return any(effect.kind == EffectKind.NO_ACTIONS for injury in injuries for effect in injury.effects)


def ends_after(injury: Injury, round_number: int) -> int | None:
    """
    이 라운드에 생긴 부상이 풀리는 라운드. 그 라운드가 닫힐 때 풀린다. 짧은 것에만 있고, 나머지는 None.

    1 라운드짜리는 다음 라운드 동안 효과가 있고, 그 라운드가 닫힐 때 풀린다.
    """
    if injury.healing != Healing.ROUNDS:
        return None
    return round_number + injury.rounds
