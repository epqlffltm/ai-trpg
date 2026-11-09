# trpg-server/app/rounds/foe_guards.py

"""
몬스터와 NPC 의 방어하기(#254). 라운드가 닫힐 때, 판정을 시작하기 전에 엔진이 누가 방어 태세를 잡는지 정한다.

서술(AI)이 정하지 않는다. 시트에 적은 때(defends)만 본다(app/assets/scenarios/schemas.py 의 Defends).
  - 고르는 쪽(decide): 이번 라운드에 차례를 받는 몬스터(살아 있고 공격이 있다)와 싸우는 인물이다. 장면의 마리 순서,
    그다음 장면의 인물 순서다. 입은 부상 때문에 움직이지 못하면(기절 같은 것) 방어하지도 못한다.
  - 정하는 법: HP 가 최대 HP 의 below 백분율 이하이면 방어한다. 아니면 chance 가 있으면 백분율의 주사위(d100)를
    굴려 chance 이하이면 방어한다. 둘 다 없으면(defends 가 null) 방어하지 않는다. 굴리는 것은 chance 를 볼 때뿐이다.
  - 방어하는 쪽은 그 라운드에 치지 않는다(차례의 outcome 이 skipped defending). 그를 노린 공격은 불리하다
    (캐릭터의 타격, 몬스터가 인물을 치는 것). 캐릭터의 방어하기와 같다(app/rounds/guards.py).
방어하는 쪽의 모음은 몬스터의 id 와 인물의 항목 id 다. 둘은 겹치지 않는다(uuid 다).

DB 를 모른다. 상태를 고치지 않는다.
"""

import uuid

from app.assets.scenarios.snapshot import DefendsSnapshot
from app.engine.dice import Dice
from app.engine.ruleset import Ruleset
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember
from app.rounds.monster_scene import SceneMonster

# 확률을 굴리는 주사위의 면 수. 백분율이다
PERCENT = 100


def is_low(hp: int, max_hp: int, below: int | None) -> bool:
    """HP 가 문턱(최대 HP 의 below 백분율) 이하인가. 문턱이 없으면 거짓이다."""
    return below is not None and hp * 100 <= below * max_hp


def wants_guard(defends: DefendsSnapshot | None, hp: int, max_hp: int, dice: Dice) -> bool:
    """
    이 라운드에 방어 태세를 잡는가. HP 의 문턱을 먼저 보고, 아니면 확률을 굴린다(확률이 있을 때만 굴린다).

    방어하는 때가 없으면 거짓이다.
    """
    if defends is None:
        return False
    if is_low(hp, max_hp, defends.below):
        return True
    return defends.chance is not None and dice.roll(PERCENT) <= defends.chance


def monster_guards(ruleset: Ruleset, monster: SceneMonster, dice: Dice) -> bool:
    """이 마리가 이 라운드에 방어 태세를 잡는가. 움직이지 못하면 방어하지도 못한다."""
    state = monster.state
    if round_injuries.is_incapacitated(ruleset, state.injuries):
        return False
    return wants_guard(monster.definition.defends, state.hp, state.max_hp, dice)


def person_guards(ruleset: Ruleset, person: CastMember, dice: Dice) -> bool:
    """이 인물이 이 라운드에 방어 태세를 잡는가. 시트가 없으면 방어하지 않는다. 움직이지 못하면 방어하지도 못한다."""
    npc = person.npc
    if person.definition is None or round_injuries.is_incapacitated(ruleset, npc.injuries):
        return False
    return wants_guard(person.definition.defends, npc.hp, npc.max_hp, dice)


def decide(
    ruleset: Ruleset, acting: list[SceneMonster], fighting: list[CastMember], dice: Dice
) -> frozenset[uuid.UUID]:
    """
    이 라운드에 방어 태세를 잡는 몬스터와 인물. 몬스터의 id 와 인물의 항목 id 다. 판정을 시작하기 전에 한 번 정한다.

    acting 은 차례를 받는 몬스터들, fighting 은 싸우는 인물들이다(app/rounds/judging.py). 그 차례로 굴린다.
    """
    guarded = {monster.state.id for monster in acting if monster_guards(ruleset, monster, dice)}
    guarded |= {person.entry_id for person in fighting if person_guards(ruleset, person, dice)}
    return frozenset(guarded)
