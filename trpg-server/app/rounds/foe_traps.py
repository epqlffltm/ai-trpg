# trpg-server/app/rounds/foe_traps.py

"""
몬스터와 싸우는 인물(NPC)이 덫을 밟는 것(#806 ②-b). 라운드의 차례에 정한다(app/rounds/monster_attacks.py,
app/rounds/npc_attacks.py).

몬스터는 장소를 옮기지 않는다. 싸우려고 다가서다 밟는다.
  - 자기 차례에 공격을 굴렸으면(맞았든 빗나갔든), 그 뒤에 그 장소에 놓인 덫 하나를 놓은 순서대로 밟는다.
    움직이지 못한 차례와 비용이 모자라 하지 못한 차례는 밟지 않는다. 한 차례에 하나다.
  - 몬스터와 인물은 테이블이 덫을 찾아냈는지 모른다. 찾아낸 덫도 밟는다.
  - 인물은 장소가 있는 인물만 밟는다(장소가 없는 인물은 덫이 있는 곳에 서 있지 않다).
  - 피하는 판정은 그 덫의 avoid 를 밟은 쪽의 능력치로 굴린다. 입은 부상의 영향을 받는다.
    못 피하면 덫의 효과가 든다. 피해는 그 등급으로(성질과 저항을 따른다, #886), 부상과 수치의 맞추기는
    물건의 효과와 같이(면역과 저항을 따른다, app/rounds/item_targets.py 의 apply_to_struck) 든다.
    피해로 죽었으면 부상과 맞추기는 들지 않는다.
    덫은 죽이려는 공격이 아니다(lethal 이 아니다). 쓰러질지 죽을지는 몬스터의 타입이 정한다.
  - 덫에 처음 쓰러졌으면 드롭을 굴린다(app/rounds/drops.py). 몬스터는 그 장소, 인물은 공격받은 사람이 선 장소다.
  - 피하든 못 피하든 덫은 터져 끝난다.

DB 를 모른다. 덫과 밟은 쪽의 상태와 드롭을 받은 사람의 소지품을 고친다. 저장하지 않는다.
"""

import uuid

from app.assets.scenarios.snapshot import ItemTrapSnapshot
from app.engine.action import ActionKind, CheckAction, Consequence, Recipient
from app.engine.check import find_difficulty, resolve_hindered
from app.engine.health import ChangeKind
from app.engine.injury import Trigger
from app.engine.item_effects import EffectKind, first_of
from app.engine.ruleset import ResourceHolder
from app.rounds import drops, resisting
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember
from app.rounds.checks import change_cast_member, change_scene_monster
from app.rounds.effects import Judging
from app.rounds.item_targets import Struck, apply_to_struck
from app.rounds.map_actions import terms_document
from app.rounds.monster_scene import SceneMonster
from app.tables import monsters as table_monsters
from app.tables import npcs, places, traps
from app.tables.models import TableMember, TableTrap
from app.tables.resources import Bearer


def first_trap(judging: Judging, place_id: uuid.UUID | None) -> TableTrap | None:
    """그 장소에 놓인 덫 가운데 먼저 놓은 것. 찾아낸 덫도 든다. 장소가 없거나 덫이 없으면 None."""
    if place_id is None:
        return None
    armed = traps.armed_at(judging.table, place_id)
    return armed[0] if armed else None


def roll_avoid(judging: Judging, bearer: Bearer, rule: ItemTrapSnapshot) -> dict:
    """밟은 쪽(몬스터나 인물의 상태)의 능력치로 피하는 판정을 굴린다. 결과에 적을 모양을 돌려준다."""
    ruleset = judging.ruleset
    difficulty = find_difficulty(ruleset, rule.avoid.difficulty)
    hindrance = round_injuries.hindrance_for(ruleset, bearer.injuries, rule.avoid.ability)
    rolled = resolve_hindered(ruleset, bearer.abilities[rule.avoid.ability], difficulty, judging.dice, hindrance)
    return terms_document(judging, rule.avoid, rolled)


def harm_check(rule: ItemTrapSnapshot, **aimed: uuid.UUID) -> CheckAction | None:
    """덫의 피해를 겨눌 판정의 모양. HP 를 바꾸는 함수가 대상과 lethal 을 읽는다. 피해가 없는 덫이면 None."""
    damage = first_of(rule.effects, EffectKind.DAMAGE)
    if damage is None:
        return None
    return CheckAction(kind=ActionKind.CHECK, ability=rule.avoid.ability, harm=damage.magnitude, **aimed)


def harm_of(rule: ItemTrapSnapshot) -> Consequence | None:
    """덫의 피해. 대상이 받는다. 피해가 없는 덫이면 None."""
    damage = first_of(rule.effects, EffectKind.DAMAGE)
    if damage is None:
        return None
    return Consequence(kind=ChangeKind.DAMAGE, magnitude=damage.magnitude, recipient=Recipient.TARGET)


def nature_of_damage(rule: ItemTrapSnapshot) -> str | None:
    """덫의 피해의 성질(#886 ③). 없으면 None."""
    damage = first_of(rule.effects, EffectKind.DAMAGE)
    return damage.nature if damage is not None else None


def trap_head(judging: Judging, trap: TableTrap, avoid: dict) -> dict:
    """밟은 덫의 결과에서 어디서, 무엇을, 누가 놓았나, 피하는 판정의 칸들."""
    return {
        'place': places.describe(judging.snapshot, trap.place_id),
        'trap_id': str(trap.id),
        'entry_id': str(trap.entry_id),
        'name': judging.items[trap.entry_id].name,
        'set_by': str(trap.set_by) if trap.set_by is not None else None,
        'avoid': avoid,
        'avoided': avoid['success'],
    }


# 피했을 때 밟은 쪽에 든 것. 아무것도 들지 않았다
SPARED = {'injured': [], 'resources': []}


def struck_effects(judging: Judging, struck: Struck, rule: ItemTrapSnapshot) -> dict:
    """덫의 부상과 수치의 맞추기를 밟은 쪽에게 낸다. 입힌 것(injured)과 맞춘 수치(resources)다."""
    applied = apply_to_struck(judging, struck, rule.effects, trigger=Trigger.TRAP)
    return {'injured': applied['injured'], 'resources': applied['resources']}


def monster_steps(judging: Judging, monster: SceneMonster) -> dict | None:
    """
    몬스터 한 마리가 그 장소의 덫 하나를 밟는다. 밟은 일을 문서로 돌려준다. 덫이 없으면 None.

    못 피했으면 마리의 변화(monster_effect), 입힌 부상(injured), 맞춘 수치(resources)가 있다.
    처음 쓰러졌으면 드롭(drop)도 있다.
    """
    trap = first_trap(judging, monster.state.place_id)
    if trap is None:
        return None
    rule = judging.items[trap.entry_id].trap
    traps.spring(trap)
    head = trap_head(judging, trap, roll_avoid(judging, monster.state, rule))
    if head['avoided']:
        return {**head, 'monster_effect': None, **SPARED}
    check, harm = harm_check(rule, monster=monster.state.id), harm_of(rule)
    effect = change_scene_monster(judging, check, harm, nature=nature_of_damage(rule)) if harm else None
    struck = Struck(monster.state, ResourceHolder.MONSTERS, None, lambda: resisting.of_monster(judging, monster))
    landed = SPARED if table_monsters.is_dead(monster.state) else struck_effects(judging, struck, rule)
    stepped = {**head, 'monster_effect': effect, **landed}
    drop = drops.drop_after(judging, effect)
    return stepped if drop is None else {**stepped, 'drop': drop}


def npc_steps(judging: Judging, person: CastMember, victim: TableMember) -> dict | None:
    """
    싸우는 인물 하나가 그 장소의 덫 하나를 밟는다. 밟은 일을 문서로 돌려준다. 장소가 없거나 덫이 없으면 None.

    victim 은 그 차례에 공격받은 사람이다. 덫에 처음 쓰러진 인물의 드롭을 받는 장소가 그 사람이 선 곳이다.
    못 피했으면 인물의 변화(npc_effect), 입힌 부상(injured), 맞춘 수치(resources)가 있다.
    처음 쓰러졌으면 드롭(drop)도 있다.
    """
    trap = first_trap(judging, person.npc.place_id)
    if trap is None:
        return None
    rule = judging.items[trap.entry_id].trap
    traps.spring(trap)
    head = trap_head(judging, trap, roll_avoid(judging, person.npc, rule))
    if head['avoided']:
        return {**head, 'npc_effect': None, **SPARED}
    check, harm = harm_check(rule, npc=person.entry_id), harm_of(rule)
    effect = change_cast_member(judging, check, harm, nature=nature_of_damage(rule)) if harm else None
    struck = Struck(person.npc, ResourceHolder.NPCS, None, lambda: resisting.of_cast(judging, person))
    landed = SPARED if npcs.is_dead(person.npc) else struck_effects(judging, struck, rule)
    stepped = {**head, 'npc_effect': effect, **landed}
    drop = drops.npc_drop_after(judging, victim, effect)
    return stepped if drop is None else {**stepped, 'drop': drop}


def with_trap(outcome: dict, stepped: dict | None) -> dict:
    """차례의 결과에 밟은 덫을 붙인다. 밟지 않았으면 그대로다(덫이 생기기 전의 결과와 같은 모양)."""
    return outcome if stepped is None else {**outcome, 'trap': stepped}
