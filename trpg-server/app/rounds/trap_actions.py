# trpg-server/app/rounds/trap_actions.py

"""
덫(#806). 놓는 행동(set_trap), 장소에 들어온 캐릭터가 덫을 터뜨리는 것, 찾기와 해제(#806 ①-b).
라운드가 닫힐 때 차례대로 정한다.

  - 놓기: 차례가 오면 가진 덫 물건 하나를 그때 서 있는 장소에 숨겨 놓는다. 소지품에서 하나 빠진다.
    받은 뒤로 그 물건을 쓰거나 건네 가지고 있지 않으면 놓지 않고 까닭(not_held)을 적는다.
  - 터뜨리기: 가기(move)로 그 장소에 들어온 캐릭터마다, 그 장소에 아직 놓인 덫을 놓은 순서대로 터뜨린다.
    덫마다 그 덫의 피하는 판정(능력과 난이도)을 굴린다. 부상의 영향은 판정하는 행동과 같다.
    실패하면 덫의 효과(피해, 부상, 수치의 맞추기)가 든다. 저항(#886)을 따른다. 피하든 못 피하든 덫은 터져 끝난다.
    놓은 사람과 일행도 걸린다. 놓은 자리를 따로 기억하지 않는다. 같은 라운드에 놓은 덫도 놓은 차례 뒤부터 터진다.
    덫에 걸려 죽었으면 그 장소의 남은 덫은 터지지 않는다. 테이블이 찾아낸 덫은 밟지 않는다.
  - 찾기: 찾기 행동(search)이 숨긴 길과 물건과 함께 그 장소의 아직 찾지 못한 덫마다 찾는 판정을 굴린다
    (덫의 find, 비었으면 피하는 판정). 찾으면 테이블 모두가 안다. 못 찾은 판정은 아무 데도 적지 않는다.
  - 해제(disarm): 찾아낸 덫 하나를 덫의 해제 판정으로 굴린다. 성공하면 덫을 거둬 그 물건을 갖는다(가득이면 그 자리에
    보이게 둔다). 실패하면 덫은 그대로다. 목표보다 BIG_MISS 이상 모자라면 덫이 해제하던 사람에게 터진다
    (피하는 판정 없이 효과가 든다). 차례가 왔을 때 앞사람이 거뒀거나 터뜨렸으면 굴리지 않는다(gone).
  업혀 들어온 사람(carry)과, 사건이 옮긴 사람은 아직 터뜨리지 않는다. 몬스터와 NPC 도 아직이다(#806 ②).

DB 를 모른다. 시트의 소지품과 테이블의 덫과 걸린 사람의 상태를 고친다. 저장하지 않는다.
"""

import uuid

from app.assets.scenarios.snapshot import ItemTrapSnapshot, TrapCheckSnapshot
from app.engine.action import DisarmAction, SetTrapAction
from app.engine.check import Check
from app.engine.injury import Trigger
from app.rounds.effects import Judging
from app.rounds.item_actions import apply_to_member
from app.rounds.map_actions import roll_terms, terms_document
from app.rounds.place_item_actions import Reason
from app.tables import items, place_items, places, sheets, traps
from app.tables.models import TableMember, TableTrap

# 덫을 피했을 때 효과의 칸들. 아무것도 들지 않았다
UNTOUCHED = {'effect': None, 'injured': [], 'resources': []}
# 해제에 이만큼 이상 모자라게 실패하면 덫이 터진다
BIG_MISS = 5


class DisarmReason:
    """해제를 굴리지 못한 까닭. 결과의 reason 에 적는다."""

    # 차례가 왔을 때 그 덫이 이미 끝났다(앞사람이 거뒀거나 터뜨렸다)
    GONE = 'gone'
    # 차례가 왔을 때 그 덫이 서 있는 장소에 없었다(그사이 옮겨졌다)
    ELSEWHERE = 'elsewhere'


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
    applied = UNTOUCHED if avoided else effects_on(judging, member, rule)
    return {
        'trap_id': str(trap.id),
        'entry_id': str(trap.entry_id),
        'name': item.name,
        'set_by': str(trap.set_by) if trap.set_by is not None else None,
        'avoid': terms_document(judging, rule.avoid, rolled),
        'avoided': avoided,
        **applied,
    }


def spring_on_arrival(judging: Judging, member: TableMember) -> list[dict]:
    """
    방금 들어온 캐릭터가 그 장소에 놓인 덫을 놓은 순서대로 터뜨린다. 터진 것들을 문서로 돌려준다.

    덫에 걸려 죽었으면 남은 덫은 그대로 둔다(다음에 들어오는 쪽의 것이다).
    """
    sprung = []
    for trap in traps.hidden_at(judging.table, member.sheet.place_id):
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


def finding_check(rule: ItemTrapSnapshot) -> TrapCheckSnapshot:
    """숨긴 덫을 찾는 판정. 덫에 적힌 찾기 판정, 없으면 피하는 판정이다."""
    return rule.find or rule.avoid


def search_traps(judging: Judging, member: TableMember) -> list[dict]:
    """
    지금 장소의 아직 찾지 못한 덫마다 찾는 판정을 굴린다. 찾은 것을 테이블이 알게 되고, 찾은 것만 문서로 돌려준다.

    같은 라운드에 앞사람이 먼저 찾은 덫은 다시 굴리지 않는다. 못 찾은 판정은 적지 않는다(숨긴 물건과 같다).
    """
    here = member.sheet.place_id
    if here is None:
        return []
    return [
        found_document(judging, trap) for trap in traps.hidden_at(judging.table, here) if finds(judging, member, trap)
    ]


def finds(judging: Judging, member: TableMember, trap: TableTrap) -> bool:
    """덫 하나를 찾는 판정을 굴린다. 찾았으면 테이블이 알게 된다. 찾았는가."""
    found = roll_terms(judging, member, finding_check(judging.items[trap.entry_id].trap)).check.success
    if found:
        traps.uncover(trap)
    return found


def found_document(judging: Judging, trap: TableTrap) -> dict:
    """찾아낸 덫 하나를 결과에 적을 모양."""
    return {'trap_id': str(trap.id), 'entry_id': str(trap.entry_id), 'name': judging.items[trap.entry_id].name}


def disarm_blocker(trap: TableTrap | None, here: uuid.UUID | None) -> str | None:
    """차례가 왔을 때 해제를 굴리지 못하는 까닭. 굴릴 수 있으면 None."""
    if trap is None or not traps.is_armed(trap):
        return DisarmReason.GONE
    if trap.place_id != here:
        return DisarmReason.ELSEWHERE
    return None


def is_big_miss(check: Check) -> bool:
    """해제에 크게 실패했는가. 목표보다 BIG_MISS 이상 모자랐다."""
    return not check.success and check.target - check.total >= BIG_MISS


def effects_on(judging: Judging, member: TableMember, rule: ItemTrapSnapshot) -> dict:
    """덫의 효과가 그 사람에게 든다. HP 의 변화(effect), 입힌 부상(injured), 맞춘 수치(resources)를 돌려준다."""
    applied = apply_to_member(judging, member, rule.effects, trigger=Trigger.TRAP)
    return {key: applied[key] for key in UNTOUCHED}


def keep_trap(judging: Judging, member: TableMember, trap: TableTrap) -> int:
    """
    거둔 덫 물건을 해제한 사람이 갖는다. 가진 개수(0 또는 1)를 돌려준다.

    한 가지의 상한에 닿아 갖지 못하면 그 장소에 보이게 둔다. 없어지지 않는다.
    """
    kept = items.add_up_to(judging.table.id, member.sheet, trap.entry_id, 1)
    if not kept:
        place_items.put_down(judging.table, trap.place_id, trap.entry_id, 1)
    return kept


def judge_disarm(judging: Judging, member: TableMember, action: DisarmAction) -> dict:
    """
    차례가 온 사람이 찾아낸 덫 하나를 해제한다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    done 이 참이면 거뒀다(kept 는 가진 개수). 거짓이면 덫은 그대로이거나, 크게 실패해 터졌다(sprung).
    굴리지 못했으면 reason 이 있고 check 는 None 이다.
    """
    trap = traps.find_trap(judging.table, action.trap)
    blocker = disarm_blocker(trap, member.sheet.place_id)
    if blocker is not None:
        return {'disarm': unrolled_disarm(judging, member, action, trap, blocker)}
    return {'disarm': rolled_disarm(judging, member, trap)}


def disarm_head(judging: Judging, member: TableMember, trap_id: uuid.UUID, entry_id: uuid.UUID | None) -> dict:
    """해제의 결과에서 누가, 어디서, 어느 덫을 다뤘는지의 칸들."""
    return {
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'place': places.describe(judging.snapshot, member.sheet.place_id),
        'trap_id': str(trap_id),
        'entry_id': str(entry_id) if entry_id is not None else None,
        'name': judging.items[entry_id].name if entry_id is not None else None,
    }


def unrolled_disarm(
    judging: Judging, member: TableMember, action: DisarmAction, trap: TableTrap | None, reason: str
) -> dict:
    """굴리지 못한 해제의 결과."""
    head = disarm_head(judging, member, action.trap, trap.entry_id if trap is not None else None)
    return {**head, 'done': False, 'reason': reason, 'check': None, 'sprung': False, **UNTOUCHED, 'kept': 0}


def rolled_disarm(judging: Judging, member: TableMember, trap: TableTrap) -> dict:
    """해제를 굴린 결과. 성공하면 거두고, 크게 실패하면 덫이 해제하던 사람에게 터진다."""
    rule = judging.items[trap.entry_id].trap
    rolled = roll_terms(judging, member, rule.disarm)
    done, sprung = rolled.check.success, is_big_miss(rolled.check)
    if done:
        traps.disarm(trap)
    if sprung:
        traps.spring(trap)
    applied = effects_on(judging, member, rule) if sprung else UNTOUCHED
    return {
        **disarm_head(judging, member, trap.id, trap.entry_id),
        'done': done,
        'reason': None,
        'check': terms_document(judging, rule.disarm, rolled),
        'sprung': sprung,
        **applied,
        'kept': keep_trap(judging, member, trap) if done else 0,
    }
