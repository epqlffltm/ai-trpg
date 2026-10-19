# game-server/app/rounds/loots.py

"""
쓰러졌거나 죽은 대상이 지닌 물건을 빼앗는 일(#475). 선언을 받을 때 보고(app/rounds/acceptance.py 의 accept_loot),
라운드가 닫힐 때 차례가 오면 정한다(judge_loot).

방장은 PC 라서 얻는 것을 정하지 않는다(#367). 판에 적은 대상이 지닌 것(app/tables/carried.py)에서만 가져간다.
대상은 같은 장소의 몬스터 한 마리나 이번 장면의 인물이다(app/rounds/victims.py 가 같은 모양으로 본다).
  - 판정이 없다. 의식이 없는 상대의 물건을 가져가는 데에 훔치기 판정은 맞지 않다.
  - 그 줄을 통째로 갖는다. 한 가지의 상한(99)을 넘은 것은 대상이 그대로 지닌다(reason full).
  - 차례가 왔을 때 앞사람이 그 물건을 먼저 가져갔으면 못 가져간다(reason gone).
  - 차례가 왔을 때 대상이 깨어 있으면(앞사람이 NPC 를 회복시켰다) 못 가져간다(reason awake). 그때는 훔치기다.
  - 한 사람이 한 라운드에 한 줄이다. 선언 하나에 행동 하나라서 따로 막지 않는다.
  - NPC 의 태도는 바꾸지 않는다. 의식이 없어서다. 쓰러져 있는(죽지 않은) 인물에게서 가져갔으면 그것을 적어 두고,
    깨어날 때 반응을 굴린다(app/rounds/wakes.py, #494).

DB 를 모른다. 대상이 지닌 것과 소지품을 고친다. 저장하지 않는다.
"""

import uuid

from app.engine.action import LootAction
from app.rounds.cast import find_cast_member
from app.rounds.effects import Judging
from app.rounds.monster_scene import Gone, find_scene_monster, stands_with
from app.rounds.victims import Victim, monster_victim, npc_victim
from app.tables import carried, items, npcs
from app.tables.models import NpcStatus, TableMember

# 빼앗아 얻은 물건의 출처. items_gained 이벤트의 source 에 적는다
LOOT_SOURCE = 'loot'


class Reason:
    """가져가지 못했거나 다 가져가지 못한 까닭. 결과의 reason 에 적는다."""

    # 차례가 왔을 때 그 물건을 대상이 더는 지니지 않았다(앞사람이 가져갔다)
    GONE = 'gone'
    # 한 가지를 가질 수 있는 개수(99)에 닿았다. 그만큼만 가져갔다
    FULL = 'full'
    # 차례가 왔을 때 대상이 깨어 있었다(앞사람이 회복시켰다)
    AWAKE = 'awake'


def describe(judging: Judging, thief: TableMember, victim: Victim, entry_id: uuid.UUID) -> dict:
    """결과의 문서에서 언제나 같은 칸들. 누가, 어느 대상에게서, 무엇을."""
    return {
        'user_id': str(thief.user_id),
        'character_name': thief.character_name,
        **victim.origin,
        'entry_id': str(entry_id),
        'name': judging.items[entry_id].name,
    }


def missed(thief: TableMember, entry_id: uuid.UUID, reason: str) -> dict:
    """아무것도 가져가지 못한 결과의 칸들. total 은 도둑이 지금 가진 개수다."""
    return {'looted': False, 'count': 0, 'left': 0, 'total': items.count_of(thief.sheet, entry_id), 'reason': reason}


def take(judging: Judging, thief: TableMember, victim: Victim, entry_id: uuid.UUID) -> dict:
    """
    대상이 지닌 그 줄을 도둑에게 옮긴다. 상한까지만 갖고 남은 것은 대상이 지닌다.

    count 는 가져간 개수, left 는 대상에게 남은 개수, total 은 도둑이 가진 개수다.
    지니지 않았으면 reason gone, 상한에 닿았으면 reason full 이다. 이미 가득이면 하나도 못 가져간다(looted 거짓).
    """
    line = carried.find_carried(victim.held, entry_id)
    if line is None:
        return missed(thief, entry_id, Reason.GONE)
    taken = items.add_up_to(judging.table.id, thief.sheet, line.entry_id, line.count)
    victim.set_count(line.slot, line.count - taken)
    return {
        'looted': taken > 0,
        'count': taken,
        'left': line.count - taken,
        'total': items.count_of(thief.sheet, entry_id),
        'reason': Reason.FULL if taken < line.count else None,
    }


def loot_from(judging: Judging, thief: TableMember, victim: Victim, awake: bool, entry_id: uuid.UUID) -> dict:
    """대상에게서 그 물건을 가져간다. 깨어 있으면 가져가지 못한다(reason awake). 결과의 loot 문서를 돌려준다."""
    result = missed(thief, entry_id, Reason.AWAKE) if awake else take(judging, thief, victim, entry_id)
    return {'loot': {**describe(judging, thief, victim, entry_id), **result}}


def judge_monster_loot(judging: Judging, thief: TableMember, action: LootAction) -> dict:
    """
    몬스터에게서 빼앗는다. 그 마리가 장면에 없거나 다른 장소에 있으면 target_gone 이다(판정과 같은 모양).

    죽은 마리에게서도 빼앗는다. 몬스터는 회복하지 않으므로 받을 때 쓰러져 있던 마리는 차례가 올 때도 쓰러져 있다.
    """
    monster = find_scene_monster(judging.monsters, action.monster)
    if monster is None:
        return {'target_gone': {'monster_id': str(action.monster), 'name': None, 'reason': Gone.ELSEWHERE}}
    if not stands_with(thief, monster):
        return {'target_gone': {'monster_id': str(monster.state.id), 'name': monster.name, 'reason': Gone.ELSEWHERE}}
    awake = monster.state.status == NpcStatus.ALIVE
    return loot_from(judging, thief, monster_victim(monster), awake, action.item)


def judge_npc_loot(judging: Judging, thief: TableMember, action: LootAction) -> dict:
    """
    NPC 에게서 빼앗는다. 죽은 인물에게서도 빼앗는다. 앞사람이 회복시켜 깨어 있으면 가져가지 못한다.

    장면의 인물은 라운드 동안 바뀌지 않으므로, 받을 때 장면에 있던 인물은 차례가 올 때도 있다.
    """
    person = find_cast_member(judging.cast, action.npc)
    if person is None:
        return {'target_gone': {'npc_id': str(action.npc), 'name': None, 'reason': Gone.ELSEWHERE}}
    awake = person.npc.status == NpcStatus.ALIVE
    result = loot_from(judging, thief, npc_victim(person), awake, action.item)
    if result['loot']['looted']:
        npcs.mark_robbed(person.npc, judging.round_number)
    return result


def judge_loot(judging: Judging, thief: TableMember, action: LootAction) -> dict:
    """차례가 온 사람이 빼앗는다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다."""
    if action.monster is not None:
        return judge_monster_loot(judging, thief, action)
    return judge_npc_loot(judging, thief, action)
