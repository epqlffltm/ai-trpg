# game-server/app/rounds/steals.py

"""
몬스터가 지닌 물건을 훔치는 일(#456). 선언을 받을 때 보고(app/rounds/acceptance.py 의 accept_steal),
라운드가 닫힐 때 차례가 오면 정한다(judge_steal).

방장은 PC 라서 얻는 것을 정하지 않는다(#367). 판에 적은 몬스터가 지닌 것(app/tables/monster_items.py)에서만 훔친다.
  - 판정: 규칙(Ruleset.steal)이 정한 능력으로 한 번 굴린다. 부상의 영향은 다른 판정과 같다.
  - 목표값(steal_odds): 규칙의 난이도에서 시작해 걸리는 만큼 오르내린다. 1 보다 낮아지지 않는다.
      오른다: 대상의 눈치 능력치의 보정, 장비, 물건의 등급(노말에서 한 단계마다).
      내린다: 둔한 타입, 둔하다고 적은 대상, 싸움 전(쓰러져 있어도), 이번 라운드에 다른 사람과 싸우는 중.
  - 성공하면 그 줄을 통째로 갖는다. 한 가지의 상한(99)을 넘으면 넘은 것은 그 마리가 그대로 지닌다.
  - 실패하면 들켰다. 그 마리와 싸운 것이 되고, 그 마리는 이번 라운드의 차례에 도둑을 친다(차례가 이미 지났으면 없다).
  - 차례가 왔을 때 그 마리가 죽었거나, 앞사람이 그 물건을 먼저 가져갔으면 굴리지 않고 까닭을 적는다.

DB 를 모른다. 몬스터가 지닌 것과 소지품을 고친다. 저장하지 않는다.
"""

import uuid
from dataclasses import asdict, dataclass

from app.assets.models import RARITY_ORDER
from app.engine.action import StealAction
from app.engine.check import find_difficulty, modifier_of, resolve_hindered
from app.engine.ruleset import Ruleset, Steal
from app.rounds import injuries as round_injuries
from app.rounds.effects import Judging, mark_fight
from app.rounds.errors import ActionNotInRulesError
from app.rounds.monster_scene import Gone, SceneMonster, find_scene_monster, gone_reason
from app.tables import items, monster_items
from app.tables.items import CatalogItem
from app.tables.models import NpcStatus, TableMember
from app.tables.monster_items import Carried

# 훔쳐 얻은 물건의 출처. items_gained 이벤트의 source 에 적는다. 몬스터의 드롭은 monster 다
STEAL_SOURCE = 'steal'


class Reason:
    """훔치지 못한 까닭 중 굴리기 전의 것. 결과의 reason 에 적는다. 들킨 것은 stolen 이 거짓이고 reason 이 없다."""

    # 차례가 왔을 때 그 물건을 그 마리가 더는 지니지 않았다(앞사람이 훔쳤다)
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


def find_carried(monster: SceneMonster, entry_id: uuid.UUID) -> Carried | None:
    """그 마리가 지금 지닌 그 물건의 줄. 지니지 않았으면 None."""
    return next(
        (one for one in monster_items.carried(monster.state, monster.definition) if one.entry_id == entry_id), None
    )


def awareness_of(ruleset: Ruleset, rule: Steal, monster: SceneMonster) -> int:
    """대상의 눈치 능력치의 보정. 규칙이 눈치를 보지 않으면 0 이다. 둔하면 음수다."""
    if rule.awareness is None:
        return 0
    return modifier_of(ruleset, monster.state.abilities[rule.awareness])


def dull_kind_of(rule: Steal, monster: SceneMonster) -> int:
    """대상의 타입이 둔한 타입이면 내릴 양. 아니면 0 이다."""
    return next((dull.amount for dull in rule.dull_kinds if dull.kind == monster.definition.kind), 0)


def is_unwary(monster: SceneMonster) -> bool:
    """싸움 전인가. 아직 아무와도 싸우지 않았거나, 쓰러져 있다."""
    return monster.state.fought_round is None or monster.state.status == NpcStatus.DOWNED


def is_distracted(judging: Judging, monster: SceneMonster, thief: TableMember) -> bool:
    """이번 라운드에 도둑의 차례 전에 그 마리가 도둑 아닌 사람과 싸웠는가."""
    return bool(judging.fights.get(monster.state.id, set()) - {thief.user_id})


def steal_odds(
    judging: Judging, rule: Steal, monster: SceneMonster, carried: Carried, thing: CatalogItem, thief: TableMember
) -> StealOdds:
    """훔치기의 목표값. 규칙의 난이도에서 시작해 걸리는 것마다 오르내린다. 1 보다 낮아지지 않는다."""
    candidates = {
        Factor.EQUIPPED: rule.equipped if carried.equipped else 0,
        Factor.RARITY: rule.rarity_step * RARITY_ORDER.index(thing.rarity),
        Factor.DULL_KIND: -dull_kind_of(rule, monster),
        Factor.DULL: -rule.dull if monster.definition.dull else 0,
        Factor.UNWARY: -rule.unwary if is_unwary(monster) else 0,
        Factor.DISTRACTED: -rule.distracted if is_distracted(judging, monster, thief) else 0,
    }
    amounts = {factor: amount for factor, amount in candidates.items() if amount}
    base = find_difficulty(judging.ruleset, rule.difficulty).target
    raw = base + awareness_of(judging.ruleset, rule, monster) + sum(amounts.values())
    return StealOdds(target=max(1, raw), amounts=amounts)


def take_line(judging: Judging, thief: TableMember, monster: SceneMonster, carried: Carried) -> int:
    """훔친 줄을 도둑에게 옮긴다. 상한까지만 갖고 남은 것은 그 마리가 지닌다. 가진 개수를 돌려준다."""
    taken = items.add_up_to(judging.table.id, thief.sheet, carried.entry_id, carried.count)
    monster_items.set_count(monster.state, carried.slot, carried.count - taken)
    return taken


def describe(judging: Judging, thief: TableMember, monster: SceneMonster, entry_id: uuid.UUID) -> dict:
    """결과의 문서에서 언제나 같은 칸들. 누가, 어느 마리에게서, 무엇을."""
    return {
        'user_id': str(thief.user_id),
        'character_name': thief.character_name,
        'monster_id': str(monster.state.id),
        'monster_name': monster.name,
        'entry_id': str(entry_id),
        'name': judging.items[entry_id].name,
    }


def roll_steal(judging: Judging, thief: TableMember, monster: SceneMonster, carried: Carried) -> dict:
    """
    훔치는 판정을 굴리고 정한다. 결과의 문서를 돌려준다.

    check 는 굴린 판정(눈, 보정, 합, 목표값, 성공)이다. factors 는 목표값을 오르내리게 한 것들이다.
    성공하면 줄을 옮긴다(count 는 훔친 개수, left 는 그 마리에게 남은 개수, total 은 도둑이 가진 개수).
    실패하면 들켜 그 마리와 싸운 것이 된다.
    """
    rule = judging.ruleset.steal
    odds = steal_odds(judging, rule, monster, carried, judging.items[carried.entry_id], thief)
    difficulty = find_difficulty(judging.ruleset, rule.difficulty).model_copy(update={'target': odds.target})
    hindrance = round_injuries.hindrance_for(judging.ruleset, thief.sheet.injuries, rule.ability)
    hindered = resolve_hindered(
        judging.ruleset, thief.sheet.abilities[rule.ability], difficulty, judging.dice, hindrance
    )
    stolen = hindered.check.success
    taken = take_line(judging, thief, monster, carried) if stolen else 0
    if not stolen:
        mark_fight(judging, monster.state, thief)
        judging.provoked[monster.state.id] = thief.user_id
    return {
        'check': asdict(hindered.check),
        'hindrance': round_injuries.hindrance_document(hindered),
        'factors': sorted(odds.amounts),
        'stolen': stolen,
        'count': taken,
        'left': carried.count - taken,
        'total': items.count_of(thief.sheet, carried.entry_id),
        'reason': Reason.FULL if stolen and taken < carried.count else None,
    }


def judge_steal(judging: Judging, thief: TableMember, action: StealAction) -> dict:
    """
    차례가 온 사람이 훔친다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    그 마리를 지금 칠 수 없으면(앞사람이 죽였다) target_gone 이다. 판정을 겨눈 몬스터가 사라진 것과 같은 모양이다.
    그 물건을 이미 지니지 않았으면 굴리지 않고 reason 이 gone 이다.
    """
    monster = find_scene_monster(judging.monsters, action.monster)
    if monster is None:
        return {'target_gone': {'monster_id': str(action.monster), 'name': None, 'reason': Gone.ELSEWHERE}}
    gone = gone_reason(thief, monster)
    if gone is not None:
        return {'target_gone': {'monster_id': str(monster.state.id), 'name': monster.name, 'reason': gone}}
    carried = find_carried(monster, action.item)
    if carried is None:
        held = items.count_of(thief.sheet, action.item)
        nothing = {
            'check': None,
            'hindrance': None,
            'factors': [],
            'stolen': False,
            'count': 0,
            'left': 0,
            'total': held,
        }
        return {'steal': {**describe(judging, thief, monster, action.item), **nothing, 'reason': Reason.GONE}}
    return {'steal': {**describe(judging, thief, monster, action.item), **roll_steal(judging, thief, monster, carried)}}
