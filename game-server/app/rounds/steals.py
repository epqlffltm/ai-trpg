# game-server/app/rounds/steals.py

"""
몬스터나 NPC 가 지닌 물건을 훔치는 일(#456, #457). 선언을 받을 때 보고(app/rounds/acceptance.py 의 accept_steal),
라운드가 닫힐 때 차례가 오면 정한다(judge_steal).

방장은 PC 라서 얻는 것을 정하지 않는다(#367). 판에 적은 대상이 지닌 것(app/tables/carried.py)에서만 훔친다.
몬스터와 NPC 를 같은 모양(Victim)으로 보고 같은 규칙으로 굴린다. 다른 것은 들켰을 때뿐이다.
  - 판정: 규칙(Ruleset.steal)이 정한 능력으로 한 번 굴린다. 부상의 영향은 다른 판정과 같다.
  - 목표값(steal_odds): 규칙의 난이도에서 시작해 걸리는 만큼 오르내린다. 1 보다 낮아지지 않는다.
      오른다: 대상의 눈치 능력치의 보정, 장비, 물건의 등급(노말에서 한 단계마다).
      내린다: 둔한 타입(몬스터만), 둔하다고 적은 대상, 싸움 전(쓰러져 있어도), 이번 라운드에 다른 사람과 싸우는 중.
  - 성공하면 그 줄을 통째로 갖는다. 한 가지의 상한(99)을 넘으면 넘은 것은 대상이 그대로 지닌다.
  - 실패하면 들켰다.
      몬스터: 그 마리와 싸운 것이 되고, 그 마리는 이번 라운드의 차례에 도둑을 친다(차례가 이미 지났으면 없다).
      NPC: 적대가 된다. 그 인물의 시트가 on_caught: fight 면 싸운 것도 된다. NPC 는 아직 공격하지 않는다.
  - 차례가 왔을 때 대상이 죽었거나, 앞사람이 그 물건을 먼저 가져갔으면 굴리지 않고 까닭을 적는다.

DB 를 모른다. 대상이 지닌 것, 소지품, NPC 의 태도를 고친다. 저장하지 않는다.
"""

import uuid
from dataclasses import asdict, dataclass

from app.assets.models import RARITY_ORDER, NpcAttitude, NpcCaught
from app.engine.action import StealAction
from app.engine.check import find_difficulty, modifier_of, resolve_hindered
from app.engine.ruleset import Ruleset, Steal
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember, find_cast_member
from app.rounds.effects import Judging, mark_fight, mark_npc_fight
from app.rounds.errors import ActionNotInRulesError
from app.rounds.monster_scene import Gone, SceneMonster, find_scene_monster, gone_reason
from app.rounds.victims import Victim, monster_victim, npc_victim
from app.tables import carried, items, npcs
from app.tables.carried import Carried
from app.tables.items import CatalogItem
from app.tables.models import TableMember
from app.tables.npc_attitudes import change_attitude

# 훔쳐 얻은 물건의 출처. items_gained 이벤트의 source 에 적는다. 몬스터의 드롭은 monster 다
STEAL_SOURCE = 'steal'
# 훔치다 들켜 NPC 의 태도가 바뀐 까닭. npc_attitude_changed 이벤트의 reason 에 적는다
CAUGHT_STEALING = 'caught_stealing'


class Reason:
    """훔치지 못한 까닭 중 굴리기 전의 것. 결과의 reason 에 적는다. 들킨 것은 stolen 이 거짓이고 reason 이 없다."""

    # 차례가 왔을 때 그 물건을 대상이 더는 지니지 않았다(앞사람이 훔쳤다)
    GONE = 'gone'
    # 한 가지를 가질 수 있는 개수(99)에 닿았다. 그만큼만 훔쳤다
    FULL = 'full'


class Factor:
    """목표값을 오르내리게 한 것. 결과의 factors 에 적는다. 대상의 눈치는 늘 보므로 적지 않는다."""

    EQUIPPED = 'equipped'
    RARITY = 'rarity'
    DULL_KIND = 'dull_kind'
    DULL = 'dull'
    UNWARY = 'unwary'
    DISTRACTED = 'distracted'


@dataclass(frozen=True)
class StealOdds:
    """훔치기의 목표값과 그것을 이룬 것들. amounts 는 걸린 것마다 오르내린 양(오르면 +, 내리면 -)이다."""

    target: int
    amounts: dict[str, int]


def require_steal(ruleset: Ruleset) -> Steal:
    """이 규칙의 훔치기. 없으면 ActionNotInRulesError(kind). 이 규칙에는 훔치는 행동이 없다."""
    if ruleset.steal is None:
        raise ActionNotInRulesError('kind')
    return ruleset.steal


def awareness_of(ruleset: Ruleset, rule: Steal, victim: Victim) -> int:
    """대상의 눈치 능력치의 보정. 규칙이 눈치를 보지 않으면 0 이다. 둔하면 음수다."""
    if rule.awareness is None:
        return 0
    return modifier_of(ruleset, victim.abilities[rule.awareness])


def dull_kind_of(rule: Steal, victim: Victim) -> int:
    """대상의 타입이 둔한 타입이면 내릴 양. 아니면(타입이 없는 NPC 도) 0 이다."""
    return next((dull.amount for dull in rule.dull_kinds if dull.kind == victim.kind), 0)


def is_distracted(judging: Judging, victim: Victim, thief: TableMember) -> bool:
    """이번 라운드에 도둑의 차례 전에 그 대상이 도둑 아닌 사람과 싸웠는가."""
    return bool(judging.fights.get(victim.key, set()) - {thief.user_id})


def steal_odds(
    judging: Judging, rule: Steal, victim: Victim, line: Carried, thing: CatalogItem, thief: TableMember
) -> StealOdds:
    """훔치기의 목표값. 규칙의 난이도에서 시작해 걸리는 것마다 오르내린다. 1 보다 낮아지지 않는다."""
    candidates = {
        Factor.EQUIPPED: rule.equipped if line.equipped else 0,
        Factor.RARITY: rule.rarity_step * RARITY_ORDER.index(thing.rarity),
        Factor.DULL_KIND: -dull_kind_of(rule, victim),
        Factor.DULL: -rule.dull if victim.dull else 0,
        Factor.UNWARY: -rule.unwary if victim.unwary else 0,
        Factor.DISTRACTED: -rule.distracted if is_distracted(judging, victim, thief) else 0,
    }
    amounts = {factor: amount for factor, amount in candidates.items() if amount}
    base = find_difficulty(judging.ruleset, rule.difficulty).target
    raw = base + awareness_of(judging.ruleset, rule, victim) + sum(amounts.values())
    return StealOdds(target=max(1, raw), amounts=amounts)


def take_line(judging: Judging, thief: TableMember, victim: Victim, line: Carried) -> int:
    """훔친 줄을 도둑에게 옮긴다. 상한까지만 갖고 남은 것은 대상이 지닌다. 가진 개수를 돌려준다."""
    taken = items.add_up_to(judging.table.id, thief.sheet, line.entry_id, line.count)
    victim.set_count(line.slot, line.count - taken)
    return taken


def describe(judging: Judging, thief: TableMember, victim: Victim, entry_id: uuid.UUID) -> dict:
    """결과의 문서에서 언제나 같은 칸들. 누가, 어느 대상에게서, 무엇을."""
    return {
        'user_id': str(thief.user_id),
        'character_name': thief.character_name,
        **victim.origin,
        'entry_id': str(entry_id),
        'name': judging.items[entry_id].name,
    }


def roll_steal(judging: Judging, thief: TableMember, victim: Victim, line: Carried) -> dict:
    """
    훔치는 판정을 굴리고 정한다. 결과의 문서를 돌려준다. 들켰을 때의 일은 부른 쪽이 한다(caught_by_*).

    check 는 굴린 판정(눈, 보정, 합, 목표값, 성공)이다. factors 는 목표값을 오르내리게 한 것들이다.
    성공하면 줄을 옮긴다(count 는 훔친 개수, left 는 대상에게 남은 개수, total 은 도둑이 가진 개수).
    """
    rule = judging.ruleset.steal
    odds = steal_odds(judging, rule, victim, line, judging.items[line.entry_id], thief)
    difficulty = find_difficulty(judging.ruleset, rule.difficulty).model_copy(update={'target': odds.target})
    hindrance = round_injuries.hindrance_for(judging.ruleset, thief.sheet.injuries, rule.ability)
    hindered = resolve_hindered(
        judging.ruleset, thief.sheet.abilities[rule.ability], difficulty, judging.dice, hindrance
    )
    stolen = hindered.check.success
    taken = take_line(judging, thief, victim, line) if stolen else 0
    return {
        'check': asdict(hindered.check),
        'hindrance': round_injuries.hindrance_document(hindered),
        'factors': sorted(odds.amounts),
        'stolen': stolen,
        'count': taken,
        'left': line.count - taken,
        'total': items.count_of(thief.sheet, line.entry_id),
        'reason': Reason.FULL if stolen and taken < line.count else None,
    }


def nothing_there(thief: TableMember, entry_id: uuid.UUID) -> dict:
    """차례가 왔을 때 대상이 그 물건을 이미 지니지 않았다. 굴리지 않은 결과의 칸들."""
    return {
        'check': None,
        'hindrance': None,
        'factors': [],
        'stolen': False,
        'count': 0,
        'left': 0,
        'total': items.count_of(thief.sheet, entry_id),
        'reason': Reason.GONE,
    }


def attempt(judging: Judging, thief: TableMember, victim: Victim, entry_id: uuid.UUID) -> dict:
    """대상에게서 그 물건을 훔치려 한다. 지니지 않았으면 굴리지 않는다. 들켰는지는 is_caught 로 본다."""
    line = carried.find_carried(victim.held, entry_id)
    rolled = nothing_there(thief, entry_id) if line is None else roll_steal(judging, thief, victim, line)
    return {**describe(judging, thief, victim, entry_id), **rolled}


def is_caught(result: dict) -> bool:
    """굴렸는데 훔치지 못했다. 들켰다."""
    return result['check'] is not None and not result['stolen']


def unnoticed() -> dict:
    """들키지 않았을 때(훔쳤거나 굴리지 않았다)의 들킴 칸들."""
    return {'fight': False, 'attitude_change': None}


def caught_by_monster(judging: Judging, thief: TableMember, monster: SceneMonster) -> dict:
    """몬스터에게 들켰다. 그 마리와 싸운 것이 되고, 그 마리는 이번 라운드의 차례에 도둑을 노린다."""
    mark_fight(judging, monster.state, thief)
    judging.provoked[monster.state.id] = thief.user_id
    return {'fight': True, 'attitude_change': None}


def fights_when_caught(person: CastMember) -> bool:
    """그 인물이 들켰을 때 싸움도 붙는가. 시트의 on_caught 가 fight 일 때다. 시트가 없으면 적대만 한다."""
    return person.definition is not None and person.definition.on_caught == NpcCaught.FIGHT


def caught_by_npc(judging: Judging, thief: TableMember, person: CastMember) -> dict:
    """
    NPC 에게 들켰다. 적대가 된다(이미 적대면 바뀐 것이 없다). 시트가 정했으면 싸운 것도 된다.

    attitude_change 는 바뀐 태도(change_attitude 의 것)다. 이미 적대였으면 None 이다.
    """
    fight = fights_when_caught(person)
    if fight:
        mark_npc_fight(judging, person.npc, thief)
    change = change_attitude(person.npc, NpcAttitude.HOSTILE, CAUGHT_STEALING)
    return {'fight': fight, 'attitude_change': change}


def judge_monster_steal(judging: Judging, thief: TableMember, action: StealAction) -> dict:
    """
    몬스터에게서 훔친다. 그 마리를 지금 칠 수 없으면(앞사람이 죽였다) target_gone 이다.

    판정을 겨눈 몬스터가 사라진 것과 같은 모양이다.
    """
    monster = find_scene_monster(judging.monsters, action.monster)
    if monster is None:
        return {'target_gone': {'monster_id': str(action.monster), 'name': None, 'reason': Gone.ELSEWHERE}}
    gone = gone_reason(thief, monster)
    if gone is not None:
        return {'target_gone': {'monster_id': str(monster.state.id), 'name': monster.name, 'reason': gone}}
    result = attempt(judging, thief, monster_victim(monster), action.item)
    caught = caught_by_monster(judging, thief, monster) if is_caught(result) else unnoticed()
    return {'steal': {**result, **caught}}


def judge_npc_steal(judging: Judging, thief: TableMember, action: StealAction) -> dict:
    """
    NPC 에게서 훔친다. 그 인물이 차례가 오기 전에 죽었으면(앞사람이 죽였다) 굴리지 않고 target_gone 이다.

    장면의 인물은 라운드 동안 바뀌지 않으므로, 받을 때 장면에 있던 인물은 차례가 올 때도 있다.
    """
    person = find_cast_member(judging.cast, action.npc)
    if person is None:
        return {'target_gone': {'npc_id': str(action.npc), 'name': None, 'reason': Gone.ELSEWHERE}}
    if npcs.is_dead(person.npc):
        return {'target_gone': {'npc_id': str(person.entry_id), 'name': person.name, 'reason': Gone.DEAD}}
    result = attempt(judging, thief, npc_victim(person), action.item)
    caught = caught_by_npc(judging, thief, person) if is_caught(result) else unnoticed()
    return {'steal': {**result, **caught}}


def judge_steal(judging: Judging, thief: TableMember, action: StealAction) -> dict:
    """
    차례가 온 사람이 훔친다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    그 물건을 대상이 이미 지니지 않았으면 굴리지 않고 reason 이 gone 이다.
    fight 는 들켜 싸움이 붙었는지, attitude_change 는 들켜 바뀐 NPC 의 태도다(몬스터는 늘 None).
    """
    if action.monster is not None:
        return judge_monster_steal(judging, thief, action)
    return judge_npc_steal(judging, thief, action)
