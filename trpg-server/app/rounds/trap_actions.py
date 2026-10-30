# trpg-server/app/rounds/trap_actions.py

"""
덫(#806). 놓는 행동(set_trap)과, 장소에 들어온 캐릭터가 덫을 터뜨리는 것. 라운드가 닫힐 때 차례대로 정한다.

  - 놓기: 차례가 오면 가진 덫 물건 하나를 그때 서 있는 장소에 숨겨 놓는다. 소지품에서 하나 빠진다.
    받은 뒤로 그 물건을 쓰거나 건네 가지고 있지 않으면 놓지 않고 까닭(not_held)을 적는다.
  - 터뜨리기: 가기(move)로 그 장소에 들어온 캐릭터마다, 그 장소에 아직 놓인 덫을 놓은 순서대로 터뜨린다.
    덫마다 그 덫의 피하는 판정(능력과 난이도)을 굴린다. 부상의 영향은 판정하는 행동과 같다.
    실패하면 덫의 효과(피해, 부상, 수치의 맞추기)가 든다. 저항(#886)을 따른다. 피하든 못 피하든 덫은 터져 끝난다.
    놓은 사람과 일행도 걸린다. 놓은 자리를 따로 기억하지 않는다. 같은 라운드에 놓은 덫도 놓은 차례 뒤부터 터진다.
    덫에 걸려 죽었으면 그 장소의 남은 덫은 터지지 않는다.
  업혀 들어온 사람(carry)과, 사건이 옮긴 사람은 아직 터뜨리지 않는다. 몬스터와 NPC 도 아직이다(#806 ②).

DB 를 모른다. 시트의 소지품과 테이블의 덫과 걸린 사람의 상태를 고친다. 저장하지 않는다.
"""

from app.engine.action import SetTrapAction
from app.engine.injury import Trigger
from app.rounds.effects import Judging
from app.rounds.item_actions import apply_to_member
from app.rounds.map_actions import roll_terms, terms_document
from app.rounds.place_item_actions import Reason
from app.tables import items, places, sheets, traps
from app.tables.models import TableMember, TableTrap

# 덫을 피했을 때 효과의 칸들. 아무것도 들지 않았다
UNTOUCHED = {'effect': None, 'injured': [], 'resources': []}


def can_lay(judging: Judging, member: TableMember, action: SetTrapAction) -> bool:
    """차례가 왔을 때 덫을 놓을 수 있는가. 맵에 서 있고, 그 덫 물건을 아직 가지고 있다."""
    return member.sheet.place_id is not None and items.count_of(member.sheet, action.item) >= 1


def judge_set_trap(judging: Judging, member: TableMember, action: SetTrapAction) -> dict:
    """
    차례가 온 사람이 덫을 놓는다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    set 이 참이면 놓았다. 가지고 있지 않으면 놓지 않고 까닭(not_held)을 적는다. remaining 은 놓은 뒤에 가진 개수다.
    """
    here = member.sheet.place_id
    laid = can_lay(judging, member, action)
    if laid:
        items.remove_items(member.sheet, action.item, 1)
        traps.lay(judging.table, here, action.item, member.user_id, judging.round_number)
    return {
        'trap_set': {
            'user_id': str(member.user_id),
            'character_name': member.character_name,
            'place': places.describe(judging.snapshot, here),
            'entry_id': str(action.item),
            'name': judging.items[action.item].name,
            'set': laid,
            'reason': None if laid else Reason.NOT_HELD,
            'remaining': items.count_of(member.sheet, action.item),
        }
    }


def spring_one(judging: Judging, member: TableMember, trap: TableTrap) -> dict:
    """
    들어온 캐릭터 하나가 덫 하나를 터뜨린다. 피하는 판정을 굴리고, 실패하면 효과를 낸다. 덫은 끝난다.

    걸린 일을 문서로 돌려준다. 무엇이(entry_id, name), 누가 놓았나(set_by), 피하는 판정(avoid), 피했나(avoided),
    효과가 든 것(effect, injured, resources)이다.
    """
    item = judging.items[trap.entry_id]
    rule = item.trap
    traps.spring(trap)
    rolled = roll_terms(judging, member, rule.avoid)
    avoided = rolled.check.success
    applied = UNTOUCHED if avoided else apply_to_member(judging, member, rule.effects, trigger=Trigger.TRAP)
    return {
        'trap_id': str(trap.id),
        'entry_id': str(trap.entry_id),
        'name': item.name,
        'set_by': str(trap.set_by) if trap.set_by is not None else None,
        'avoid': terms_document(judging, rule.avoid, rolled),
        'avoided': avoided,
        'effect': applied['effect'],
        'injured': applied['injured'],
        'resources': applied['resources'],
    }


def spring_on_arrival(judging: Judging, member: TableMember) -> list[dict]:
    """
    방금 들어온 캐릭터가 그 장소에 놓인 덫을 놓은 순서대로 터뜨린다. 터진 것들을 문서로 돌려준다.

    덫에 걸려 죽었으면 남은 덫은 그대로 둔다(다음에 들어오는 쪽의 것이다).
    """
    sprung = []
    for trap in traps.armed_at(judging.table, member.sheet.place_id):
        if sheets.is_dead(member):
            break
        sprung.append(spring_one(judging, member, trap))
    return sprung


def with_traps(judging: Judging, member: TableMember, outcome: dict) -> dict:
    """
    가기의 결과에 들어간 장소의 덫을 붙인다. 갔고 덫이 터졌을 때만 move 에 traps 를 더한다.

    가지 못했으면 그대로다. 덫이 없는 장소에 들어갔어도 그대로다(덫이 생기기 전의 결과와 같은 모양).
    """
    move = outcome['move']
    if not move['moved']:
        return outcome
    sprung = spring_on_arrival(judging, member)
    return outcome if not sprung else {**outcome, 'move': {**move, 'traps': sprung}}
