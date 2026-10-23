# trpg-server/app/engine/armor.py

"""
공격이 맞는 부위와 방어구가 막는 크기(#276). 앉은 사람, NPC, 몬스터에 같은 규칙을 쓴다.

  - 부위는 규칙의 장비의 칸이다. 공격이 어느 칸에 맞는지는 서버의 주사위가 칸마다의 가중치(hit_weight)대로 굴린다.
    가중치가 0 인 칸에는 맞지 않는다. 노려 치면(strike) 굴리지 않고 그 칸이다. 대가는 노려 치기의 것이다.
  - 맞은 부위의 방어는 그 칸을 차지한 착용의 방어(defense)와 몬스터의 그 부위의 타고난 방어를 더한 것에,
    착용한 모든 물건의 모든 부위 방어(guard, 방패)를 더한 것이다.
  - 방어가 하는 일은 규칙의 방어 방식(armor.mode)이 정한다.
      ac: 맞히는 목표값이 그만큼 오른다.  reduce: 굴린 피해에서 그만큼 뺀다(0 아래로는 가지 않는다).
    방어 방식이 없는 규칙이면 방어구가 막지 않고 부위도 굴리지 않는다.

DB 를 모른다. 누가 무엇을 착용했는지는 부르는 쪽이 Worn 으로 넘긴다.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.ruleset import ArmorMode, EquipmentSlot, Ruleset


@dataclass(frozen=True)
class Worn:
    """착용한 것 하나. 차지한 칸들과, 그 물건의 차지한 칸의 방어와 모든 부위의 방어다. 없으면 0 이다."""

    slots: tuple[str, ...]
    defense: int = 0
    guard: int = 0


@dataclass(frozen=True)
class Protection:
    """한 쪽이 입은 방어. 부위마다의 방어(착용 + 타고난 것)와 모든 부위의 방어다."""

    by_slot: Mapping[str, int]
    guard: int = 0


NO_PROTECTION = Protection(by_slot={}, guard=0)


def protection_of(worn: Sequence[Worn], natural: Mapping[str, int] | None = None) -> Protection:
    """
    착용한 것들과 타고난 방어를 더해 방어로 만든다.

    여러 칸을 차지한 물건은 그 칸들 모두에 그 방어를 준다. 한 칸에 두 착용이 겹치지 않는 것은 착용의 규칙이 지킨다.
    """
    by_slot = dict(natural or {})
    for one in worn:
        for slot in one.slots:
            by_slot[slot] = by_slot.get(slot, 0) + one.defense
    return Protection(by_slot=by_slot, guard=sum(one.guard for one in worn))


def defense_at(protection: Protection, slot: str | None) -> int:
    """그 부위의 방어. 부위가 없으면(굴리지 않았다) 모든 부위의 방어만이다."""
    return protection.by_slot.get(slot, 0) + protection.guard if slot is not None else protection.guard


def varies_by_slot(protection: Protection) -> bool:
    """부위에 따라 방어가 다른가. 어느 부위에라도 방어가 있어야 한다. 없으면 어디에 맞아도 같다."""
    return any(defense > 0 for defense in protection.by_slot.values())


def hittable(ruleset: Ruleset) -> list[EquipmentSlot]:
    """맞을 수 있는 칸들. 규칙의 차례다. 가중치가 0 인 칸은 뺀다."""
    return [slot for slot in ruleset.equipment_slots if slot.hit_weight > 0]


def can_strike(ruleset: Ruleset, slot: str) -> bool:
    """그 칸을 노려 칠 수 있는가. 방어 방식과 노려 치기가 있는 규칙이고, 맞을 수 있는 칸이어야 한다."""
    if ruleset.armor is None or ruleset.called_shot is None:
        return False
    return any(one.key == slot for one in hittable(ruleset))


def roll_location(ruleset: Ruleset, dice: Dice) -> str | None:
    """
    공격이 맞은 부위를 굴린다. 칸마다의 가중치대로다. 칸이 하나뿐이면 굴리지 않는다.

    방어 방식이 없거나 맞을 수 있는 칸이 없으면 굴리지 않고 None 이다.
    """
    slots = hittable(ruleset) if ruleset.armor is not None else []
    if not slots:
        return None
    if len(slots) == 1:
        return slots[0].key
    point = dice.roll(sum(slot.hit_weight for slot in slots))
    for slot in slots:
        point -= slot.hit_weight
        if point <= 0:
            return slot.key
    return slots[-1].key


def target_raise(ruleset: Ruleset, defense: int) -> int:
    """맞히는 목표값을 올리는 양. 방어 방식이 ac 일 때만 방어만큼이다."""
    return defense if ruleset.armor is not None and ruleset.armor.mode == ArmorMode.AC else 0


def damage_cut(ruleset: Ruleset, defense: int) -> int:
    """맞은 피해에서 깎는 양. 방어 방식이 reduce 일 때만 방어만큼이다."""
    return defense if ruleset.armor is not None and ruleset.armor.mode == ArmorMode.REDUCE else 0
